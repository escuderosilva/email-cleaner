"""Write-back del estado de validación a HubSpot.

Usa la API v3 del CRM con un token de private app (variable de entorno
HUBSPOT_TOKEN). Escribe el estado en una propiedad custom de contacto.

Por defecto corre en dry_run: NO toca el CRM, solo devuelve lo que enviaría.
Confirma el resultado del dry-run antes de correr en real.
"""
import os

import requests

BASE = "https://api.hubapi.com"

# Propiedades custom de contacto que escribe la herramienta.
PROPERTY_NAME = "email_validation_status"      # estado (válido/riesgo/inválido)
PROPERTY_OWNER = "email_validation_owner"      # correo de quien hizo el chequeo
PROPERTY_DATE = "email_validation_last_date"   # fecha de la última verificación

# Definiciones de cada propiedad para crearlas si no existen.
PROPERTY_DEFS = {
    PROPERTY_NAME: {
        "name": PROPERTY_NAME,
        "label": "Estado validación email",
        "type": "enumeration",
        "fieldType": "select",
        "groupName": "contactinformation",
        "options": [
            {"label": "Válido", "value": "valido"},
            {"label": "Riesgo", "value": "riesgo"},
            {"label": "Inválido", "value": "invalido"},
        ],
    },
    PROPERTY_OWNER: {
        "name": PROPERTY_OWNER,
        "label": "Validado por",
        # Propiedad que referencia a un usuario/owner de HubSpot: el valor es el
        # owner id, así queda asociada al perfil de la persona, no como texto.
        "type": "enumeration",
        "fieldType": "select",
        "referencedObjectType": "OWNER",
        "externalOptions": True,
        "groupName": "contactinformation",
    },
    PROPERTY_DATE: {
        "name": PROPERTY_DATE,
        "label": "Última verificación email",
        "type": "date",
        "fieldType": "date",
        "groupName": "contactinformation",
    },
}


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_token(token: str = None) -> str:
    token = token or os.environ.get("HUBSPOT_TOKEN")
    if not token:
        raise ValueError("Falta HUBSPOT_TOKEN (variable de entorno o parámetro).")
    return token


def ensure_properties(token: str = None) -> dict:
    """Crea las propiedades custom que falten. Idempotente.

    Si la propiedad 'Validado por' quedó de una versión anterior como texto, la
    recrea como referencia a owner (migración; solo tiene sentido porque aún no
    guarda datos)."""
    token = get_token(token)
    created = []
    for name, payload in PROPERTY_DEFS.items():
        r = requests.get(
            f"{BASE}/crm/v3/properties/contacts/{name}", headers=_headers(token), timeout=20
        )
        if r.status_code == 200:
            existing = r.json()
            wanted_ref = payload.get("referencedObjectType")
            if wanted_ref and existing.get("referencedObjectType") != wanted_ref:
                # Tipo distinto al deseado: borrar y recrear.
                requests.delete(
                    f"{BASE}/crm/v3/properties/contacts/{name}", headers=_headers(token), timeout=20
                )
            else:
                continue
        rc = requests.post(
            f"{BASE}/crm/v3/properties/contacts",
            headers=_headers(token), json=payload, timeout=20,
        )
        rc.raise_for_status()
        created.append(name)
    return {"created": created}


# Alias por compatibilidad.
def ensure_property(token: str = None) -> dict:
    return ensure_properties(token)


def resolve_owner_id(email: str, token: str = None):
    """Traduce un correo al owner id de HubSpot (perfil de usuario).
    Requiere el scope crm.objects.owners.read en la Service Key."""
    token = get_token(token)
    r = requests.get(
        f"{BASE}/crm/v3/owners", headers=_headers(token),
        params={"email": email}, timeout=20,
    )
    if r.status_code == 403:
        raise ValueError(
            "La Service Key no tiene el scope 'crm.objects.owners.read'. "
            "Agrégalo en HubSpot para poder asociar el validador a su perfil."
        )
    r.raise_for_status()
    results = r.json().get("results", [])
    for o in results:
        if o.get("email", "").lower() == email.lower():
            return o.get("id")
    return results[0].get("id") if results else None


def build_inputs(df, owner_id: str = None, email_col: str = "email_normalizado",
                 status_col: str = "estado") -> list:
    """Construye el payload de batch update. Solo filas con email y no duplicadas.
    Escribe estado, fecha de verificación y (si se pasa) el owner id del validador."""
    inputs = []
    for _, row in df.iterrows():
        email = str(row.get(email_col, "")).strip()
        if not email or row.get("es_duplicado", False):
            continue
        props = {PROPERTY_NAME: row[status_col]}
        fecha = str(row.get("last_check_date", "")).strip()
        if fecha:
            props[PROPERTY_DATE] = fecha
        if owner_id:
            props[PROPERTY_OWNER] = owner_id
        inputs.append({"idProperty": "email", "id": email, "properties": props})
    return inputs


def resolve_contact_ids(emails, token: str, batch_size: int = 100) -> dict:
    """Resuelve email -> contactId en HubSpot (solo lectura). Los que no existen se omiten."""
    ids = {}
    url = f"{BASE}/crm/v3/objects/contacts/batch/read"
    for i in range(0, len(emails), batch_size):
        chunk = emails[i:i + batch_size]
        payload = {
            "idProperty": "email",
            "properties": ["email"],
            "inputs": [{"id": e} for e in chunk],
        }
        r = requests.post(url, headers=_headers(token), json=payload, timeout=30)
        if r.status_code < 300:
            for res in r.json().get("results", []):
                email = res.get("properties", {}).get("email", "").lower()
                if email:
                    ids[email] = res["id"]
    return ids


def archive_invalids(df, token: str = None, dry_run: bool = True, batch_size: int = 100) -> dict:
    """Archiva en HubSpot los contactos marcados 'invalido' (no duplicados).

    Archivar = enviar a la papelera de HubSpot; recuperable ~90 días. No es borrado
    permanente. En dry_run solo resuelve cuáles existen en el CRM, sin archivar nada.
    """
    invalid = df[
        (df["estado"] == "invalido")
        & (~df.get("es_duplicado", False))
        & (df["email_normalizado"] != "")
    ]
    emails = invalid["email_normalizado"].tolist()
    summary = {
        "invalidos_en_csv": len(emails),
        "dry_run": dry_run,
        "existen_en_hubspot": 0,
        "archivados": 0,
        "muestra_a_archivar": [],
        "errores": [],
    }
    if not emails:
        return summary

    token = get_token(token)
    ids_map = resolve_contact_ids(emails, token, batch_size)
    summary["existen_en_hubspot"] = len(ids_map)
    summary["muestra_a_archivar"] = list(ids_map.keys())[:5]

    if dry_run or not ids_map:
        return summary

    contact_ids = list(ids_map.values())
    url = f"{BASE}/crm/v3/objects/contacts/batch/archive"
    for i in range(0, len(contact_ids), batch_size):
        chunk = contact_ids[i:i + batch_size]
        r = requests.post(
            url, headers=_headers(token),
            json={"inputs": [{"id": cid} for cid in chunk]}, timeout=30,
        )
        if r.status_code >= 300:
            summary["errores"].append({"lote_inicio": i, "status": r.status_code, "body": r.text[:300]})
        else:
            summary["archivados"] += len(chunk)
    return summary


def sync_statuses(df, token: str = None, owner: str = None,
                  dry_run: bool = True, batch_size: int = 100) -> dict:
    """Escribe estado, fecha de verificación y validador por contacto.
    El validador (owner) se resuelve a su owner id de HubSpot para quedar asociado
    a su perfil. dry_run=True no escribe, pero sí resuelve el owner para validarlo."""
    owner_id = None
    validado_por = "(sin owner)"
    if owner:
        token = get_token(token)
        owner_id = resolve_owner_id(owner, token)
        if not owner_id:
            raise ValueError(
                f"'{owner}' no es un usuario de HubSpot; no se puede asociar como validador."
            )
        validado_por = f"{owner} (owner id {owner_id})"

    inputs = build_inputs(df, owner_id=owner_id)
    summary = {
        "total_a_actualizar": len(inputs),
        "dry_run": dry_run,
        "validado_por": validado_por,
        "muestra": inputs[:5],
        "lotes": (len(inputs) + batch_size - 1) // batch_size,
        "actualizados": 0,
        "errores": [],
    }
    if dry_run or not inputs:
        return summary

    token = get_token(token)
    ensure_properties(token)
    url = f"{BASE}/crm/v3/objects/contacts/batch/update"
    for i in range(0, len(inputs), batch_size):
        chunk = inputs[i:i + batch_size]
        r = requests.post(url, headers=_headers(token), json={"inputs": chunk}, timeout=30)
        if r.status_code >= 300:
            summary["errores"].append({"lote_inicio": i, "status": r.status_code, "body": r.text[:300]})
        else:
            summary["actualizados"] += len(chunk)
    return summary
