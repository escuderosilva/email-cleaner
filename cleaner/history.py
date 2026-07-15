"""Historial persistente de chequeos, para no revalidar correos recién revisados.

Guarda por email (tal como venía en el archivo, normalizado a minúsculas) el
resultado de la última validación y su fecha. En corridas siguientes, si un
correo fue chequeado dentro de la ventana elegida, se reutiliza el resultado y
no se gasta procesamiento (ni consultas DNS) en él.
"""
import json
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "check_history.json"

FIELDS = ("last_check_date", "estado", "motivo", "tipo_dominio",
          "email_normalizado", "dominio", "correccion_typo")


def load_history() -> dict:
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_history(history: dict) -> None:
    HISTORY_PATH.write_text(json.dumps(history), encoding="utf-8")
