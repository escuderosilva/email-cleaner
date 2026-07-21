"""Control de acceso por correo corporativo y registro de uso.

El login es liviano (captura el correo, valida el dominio) y su fin es TRAZAR el
uso, no proteger secretos: alguien podría escribir cualquier correo @wherex.
Para identidad no falsificable, usar el SSO de Google de Streamlit Cloud (app
privada) — ver README.

El registro se escribe a stdout (queda en los logs de Streamlit Cloud) y a un CSV
local. Ojo: en Streamlit Cloud el CSV es efímero (se pierde al reiniciar); la
fuente durable son los logs de stdout o un destino externo (ver README).
"""
import csv
import json
import os
from datetime import datetime
from pathlib import Path

USAGE_LOG = Path(__file__).resolve().parent.parent / "data" / "usage_log.csv"
HEADER = ["timestamp", "email", "accion", "detalle"]

# Dominios corporativos permitidos para usar la herramienta.
ALLOWED_DOMAINS = {"wherex.com", "wherexpay.com"}


def is_allowed_email(email: str) -> bool:
    email = (email or "").strip().lower()
    return "@" in email and email.rsplit("@", 1)[1] in ALLOWED_DOMAINS


# ---- Google Sheet (destino durable, opcional) ----
_ws = None
_ws_init = False


def _get_worksheet():
    """Devuelve la hoja de cálculo para registrar uso, o None si no está
    configurada / falla. Se cachea para no reautenticar en cada evento."""
    global _ws, _ws_init
    if _ws_init:
        return _ws
    _ws_init = True

    sheet_id = os.environ.get("USAGE_SHEET_ID")
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if not sheet_id or not creds_json:
        return None
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        ws = gspread.authorize(creds).open_by_key(sheet_id).sheet1
        if not ws.get_all_values():
            ws.append_row(HEADER)
        _ws = ws
    except Exception:
        _ws = None
    return _ws


def log_event(email: str, action: str, detail: str = "") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 1) stdout: visible en los logs de Streamlit Cloud (Manage app -> logs).
    print(f"[USO] {ts} | {email} | {action} | {detail}", flush=True)
    # 2) CSV local (persistente en local; efímero en Cloud).
    try:
        nuevo = not USAGE_LOG.exists()
        with open(USAGE_LOG, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if nuevo:
                w.writerow(HEADER)
            w.writerow([ts, email, action, detail])
    except OSError:
        pass
    # 3) Google Sheet (durable), si está configurada. Nunca rompe la app.
    ws = _get_worksheet()
    if ws is not None:
        try:
            ws.append_row([ts, email, action, detail], value_input_option="RAW")
        except Exception:
            pass
