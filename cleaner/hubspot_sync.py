"""Write-back del estado de validación a HubSpot.

Usa la API v3 del CRM con un token de private app (variable de entorno
HUBSPOT_TOKEN). Escribe el estado en una propiedad custom de contacto.

Por defecto corre en dry_run: NO toca el CRM, solo devuelve lo que enviaría.
Confirma el resultado del dry-run antes de correr en real.
"""
import os

import requests

BASE = "https://api.hubapi.com"
PROPERTY_NAME = "email_validation_status"
PROPERTY_LABEL = "Estado validación email"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_token(token: str = None) -> str:
    token = token or os.environ.get("HUBSPOT_TOKEN")
    if not token:
        raise ValueError("Falta HUBSPOT_TOKEN (variable de entorno o parámetro).")
    return token


def ensure_property(token: str = None) -> dict:
    """Crea la propiedad custom si no existe. Idempotente."""
    token = get_token(token)
    url = f"{BASE}/crm/v3/properties/contacts/{PROPERTY_NAME}"
    r = requests.get(url, headers=_headers(token), timeout=20)
    if r.status_code == 200:
        return {"created": False, "property": PROPERTY_NAME}

    payload = {
        "name": PROPERTY_NAME,
        "label": PROPERTY_LABEL,
        "type": "enumeration",
        "fieldType": "select",
        "groupName": "contactinformation",
        "options": [
            {"label": "Válido", "value": "valido"},
            {"label": "Riesgo", "value": "riesgo"},
            {"label": "Inválido", "value": "invalido"},
        ],
    }
    r = requests.post(
        f"{BASE}/crm/v3/properties/contacts",
        headers=_headers(token), json=payload, timeout=20,
    )
    r.raise_for_status()
    return {"created": True, "property": PROPERTY_NAME}


def build_inputs(df, email_col: str = "email_normalizado", status_col: str = "estado") -> list:
    """Construye el payload de batch update. Solo filas con email y no duplicadas."""
    inputs = []
    for _, row in df.iterrows():
        email = str(row.get(email_col, "")).strip()
        if not email or row.get("es_duplicado", False):
            continue
        inputs.append({
            "idProperty": "email",
            "id": email,
            "properties": {PROPERTY_NAME: row[status_col]},
        })
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


def sync_statuses(df, token: str = None, dry_run: bool = True, batch_size: int = 100) -> dict:
    """Escribe el estado por contacto. dry_run=True no llama a HubSpot."""
    inputs = build_inputs(df)
    summary = {
        "total_a_actualizar": len(inputs),
        "dry_run": dry_run,
        "muestra": inputs[:5],
        "lotes": (len(inputs) + batch_size - 1) // batch_size,
        "actualizados": 0,
        "errores": [],
    }
    if dry_run or not inputs:
        return summary

    token = get_token(token)
    ensure_property(token)
    url = f"{BASE}/crm/v3/objects/contacts/batch/update"
    for i in range(0, len(inputs), batch_size):
        chunk = inputs[i:i + batch_size]
        r = requests.post(url, headers=_headers(token), json={"inputs": chunk}, timeout=30)
        if r.status_code >= 300:
            summary["errores"].append({"lote_inicio": i, "status": r.status_code, "body": r.text[:300]})
        else:
            summary["actualizados"] += len(chunk)
    return summary
