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
from datetime import datetime
from pathlib import Path

USAGE_LOG = Path(__file__).resolve().parent.parent / "data" / "usage_log.csv"

# Dominios corporativos permitidos para usar la herramienta.
ALLOWED_DOMAINS = {"wherex.com", "wherexpay.com"}


def is_allowed_email(email: str) -> bool:
    email = (email or "").strip().lower()
    return "@" in email and email.rsplit("@", 1)[1] in ALLOWED_DOMAINS


def log_event(email: str, action: str, detail: str = "") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # stdout: visible en los logs de Streamlit Cloud (Manage app -> logs).
    print(f"[USO] {ts} | {email} | {action} | {detail}", flush=True)
    # CSV local (persistente en local; efímero en Cloud).
    try:
        nuevo = not USAGE_LOG.exists()
        with open(USAGE_LOG, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if nuevo:
                w.writerow(["timestamp", "email", "accion", "detalle"])
            w.writerow([ts, email, action, detail])
    except OSError:
        pass
