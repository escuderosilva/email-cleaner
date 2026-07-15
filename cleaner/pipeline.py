from datetime import datetime, timedelta

import pandas as pd

from .domains import (
    DISPOSABLE_DOMAINS,
    FREE_DOMAINS,
    ROLE_PREFIXES,
    SUSPICIOUS_LOCAL_PARTS,
)
from .history import load_history, save_history
from .validators import check_syntax, resolve_mx_bulk, suggest_domain_typo


def _split(email: str):
    local, _, domain = email.partition("@")
    return local, domain


def _parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def clean_dataframe(
    df: pd.DataFrame,
    email_col: str,
    activity_col: str = None,
    autocorrect_typos: bool = True,
    dedup: bool = True,
    recheck_days: int = None,
    progress_callback=None,
) -> pd.DataFrame:
    """Limpia la base. Si recheck_days está seteado, reutiliza del historial los
    correos chequeados dentro de esa ventana (no los revalida).

    Nota: se opera sobre el `df` recibido sin copiarlo, para ahorrar memoria; la
    app entrega un DataFrame recién leído en cada corrida, así que es seguro."""
    emails = df[email_col].fillna("").astype(str).str.strip().str.lower()

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    history = load_history()
    cutoff = (now - timedelta(days=recheck_days)) if recheck_days else None

    n = len(emails)
    normalizados = [""] * n
    originales = list(emails)
    correcciones = [""] * n
    dominios = [""] * n
    statuses = [""] * n
    reasons = [""] * n
    tipos = [""] * n
    last_check = [""] * n
    reutilizados = [False] * n

    to_check = []

    for i, email in enumerate(emails):
        if not email:
            statuses[i] = "invalido"
            reasons[i] = "sin_email"
            last_check[i] = today
            continue

        h = history.get(email) if cutoff else None
        if h:
            hd = _parse_date(h.get("last_check_date"))
            if hd and hd >= cutoff:
                normalizados[i] = h.get("email_normalizado", email)
                correcciones[i] = h.get("correccion_typo", "")
                dominios[i] = h.get("dominio", "")
                statuses[i] = h.get("estado", "")
                reasons[i] = h.get("motivo", "")
                tipos[i] = h.get("tipo_dominio", "")
                last_check[i] = h.get("last_check_date", today)
                reutilizados[i] = True
                continue

        normalizados[i] = email
        last_check[i] = today
        to_check.append(i)

    # Clasificación rápida (sintaxis, desechable, rol) de lo que sí toca revisar.
    for i in to_check:
        email = normalizados[i]
        if not check_syntax(email):
            statuses[i] = "invalido"
            reasons[i] = "sintaxis_invalida"
            continue
        local, domain = _split(email)
        dominios[i] = domain
        if domain in DISPOSABLE_DOMAINS:
            statuses[i] = "invalido"
            reasons[i] = "dominio_desechable"
            tipos[i] = "desechable"
            continue
        if local in SUSPICIOUS_LOCAL_PARTS:
            statuses[i] = "invalido"
            reasons[i] = "buzon_sospechoso"
            tipos[i] = "personal" if domain in FREE_DOMAINS else "corporativo"
            continue
        tipos[i] = "personal" if domain in FREE_DOMAINS else "corporativo"
        statuses[i] = "pendiente_mx"
        reasons[i] = "cuenta_generica_rol" if local in ROLE_PREFIXES else ""

    # Resolución MX solo de los pendientes nuevos.
    pending_domains = {dominios[i] for i in to_check if statuses[i] == "pendiente_mx"} - {""}
    mx_results = resolve_mx_bulk(pending_domains, progress_callback=progress_callback)

    # Auto-corrección solo sobre dominios rotos (sin MX) parecidos a un free-mail válido.
    if autocorrect_typos:
        candidates = {}
        for d in {dd for dd in pending_domains if mx_results.get(dd) is False}:
            typo = suggest_domain_typo(d)
            if typo and typo != d:
                candidates[d] = typo
        if candidates:
            candidate_mx = resolve_mx_bulk(set(candidates.values()))
            confirmed = {b: g for b, g in candidates.items() if candidate_mx.get(g) is True}
            for i in to_check:
                if statuses[i] == "pendiente_mx" and dominios[i] in confirmed:
                    bad = dominios[i]
                    good = confirmed[bad]
                    local = normalizados[i].split("@", 1)[0]
                    normalizados[i] = f"{local}@{good}"
                    dominios[i] = good
                    correcciones[i] = f"{bad}->{good}"
                    tipos[i] = "personal" if good in FREE_DOMAINS else "corporativo"
                    mx_results[good] = True

    # Finalizar estado de los pendientes.
    for i in to_check:
        if statuses[i] != "pendiente_mx":
            continue
        has_mx = mx_results.get(dominios[i])
        rr = [r for r in reasons[i].split(";") if r]
        if has_mx is False:
            statuses[i] = "invalido"
            reasons[i] = ";".join(rr + ["dominio_sin_mx"])
        elif has_mx is None:
            statuses[i] = "riesgo"
            reasons[i] = ";".join(rr + ["dns_no_verificable"])
        elif rr:
            statuses[i] = "riesgo"
            reasons[i] = ";".join(rr)
        else:
            statuses[i] = "valido"
            reasons[i] = ""

    df["email_normalizado"] = normalizados
    df["email_original"] = originales
    df["correccion_typo"] = correcciones
    df["dominio"] = dominios
    df["estado"] = statuses
    df["motivo"] = reasons
    df["tipo_dominio"] = tipos
    df["last_check_date"] = last_check
    df["reutilizado"] = reutilizados

    # Actualizar historial con lo chequeado en esta corrida.
    for i in range(n):
        key = originales[i]
        if not key:
            continue
        history[key] = {
            "last_check_date": last_check[i],
            "estado": statuses[i],
            "motivo": reasons[i],
            "tipo_dominio": tipos[i],
            "email_normalizado": normalizados[i],
            "dominio": dominios[i],
            "correccion_typo": correcciones[i],
        }
    save_history(history)

    df["es_duplicado"] = False
    if dedup:
        df = _mark_duplicates(df, activity_col)

    return df


def reconcile_smtp(df, smtp_by_index: dict, strict_unverifiable: bool = False, persist: bool = True):
    """Integra los resultados SMTP al estado de la base.

    smtp_by_index: {indice_de_fila: {'smtp_estado':..., 'smtp_detalle':...}}
    - existe        -> valido (o riesgo si además es cuenta de rol)
    - no_existe     -> invalido
    - sin_mx        -> invalido
    - catch_all     -> NO cambia el estado (el SMTP no puede confirmar nada en un
                       dominio que acepta todo); solo queda en la columna smtp_estado
    - no_verificable -> riesgo (o invalido si strict_unverifiable)

    Se muta el DataFrame recibido en el sitio (sin copiar) para ahorrar memoria.
    """
    if "smtp_estado" not in df.columns:
        df["smtp_estado"] = ""
        df["smtp_detalle"] = ""

    today = datetime.now().strftime("%Y-%m-%d")
    for idx, res in smtp_by_index.items():
        se = res.get("smtp_estado", "")
        df.at[idx, "smtp_estado"] = se
        df.at[idx, "smtp_detalle"] = res.get("smtp_detalle", "")
        motivo = [m for m in str(df.at[idx, "motivo"]).split(";") if m and not m.startswith("smtp_")]

        if se == "existe":
            # El buzón responde; si era cuenta de rol sigue siendo riesgo.
            df.at[idx, "estado"] = "riesgo" if motivo else "valido"
            df.at[idx, "motivo"] = ";".join(motivo)
        elif se in ("no_existe", "sin_mx"):
            df.at[idx, "estado"] = "invalido"
            df.at[idx, "motivo"] = ";".join(motivo + [f"smtp_{se}"])
        elif se == "catch_all":
            # No se toca el estado: el dominio acepta todo, el SMTP no prueba nada.
            pass
        elif se == "no_verificable":
            df.at[idx, "estado"] = "invalido" if strict_unverifiable else "riesgo"
            df.at[idx, "motivo"] = ";".join(motivo + ["smtp_no_verificable"])
        df.at[idx, "last_check_date"] = today

    if persist:
        _persist_smtp_to_history(df, smtp_by_index)
    return df


def _persist_smtp_to_history(df, smtp_by_index: dict) -> None:
    """Guarda el veredicto refinado por SMTP en el historial, para que un buzón
    confirmado como inexistente no se revalide innecesariamente después."""
    history = load_history()
    today = datetime.now().strftime("%Y-%m-%d")
    for idx in smtp_by_index:
        key = df.at[idx, "email_original"]
        if not key:
            continue
        history[key] = {
            "last_check_date": today,
            "estado": df.at[idx, "estado"],
            "motivo": df.at[idx, "motivo"],
            "tipo_dominio": df.at[idx, "tipo_dominio"],
            "email_normalizado": df.at[idx, "email_normalizado"],
            "dominio": df.at[idx, "dominio"],
            "correccion_typo": df.at[idx, "correccion_typo"],
        }
    save_history(history)


def _mark_duplicates(df: pd.DataFrame, activity_col: str) -> pd.DataFrame:
    """Marca como duplicado todo registro con email repetido, conservando el de
    actividad más reciente (o el primero si no hay columna de fecha)."""
    has_email = df["email_normalizado"] != ""
    if activity_col and activity_col in df.columns:
        # Solo las columnas necesarias para ordenar, no una copia de todo el df.
        subset = df.loc[has_email, ["email_normalizado"]].copy()
        subset["_activity"] = pd.to_datetime(df.loc[has_email, activity_col], errors="coerce")
        subset = subset.sort_values("_activity", ascending=False, na_position="last")
    else:
        subset = df.loc[has_email, ["email_normalizado"]]
    dup_mask = subset.duplicated(subset="email_normalizado", keep="first")
    duplicate_index = subset.index[dup_mask]
    df.loc[duplicate_index, "es_duplicado"] = True
    return df
