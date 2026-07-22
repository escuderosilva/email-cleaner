import os
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / "data"


def data_dir() -> Path:
    """Directorio donde la app escribe archivos de estado (caché MX, historial de
    chequeos, log de uso). Se puede apuntar a un volumen persistente con la
    variable EMAIL_CLEANER_DATA_DIR (útil en Docker/servidor). Por defecto usa la
    carpeta data/ del proyecto."""
    d = Path(os.environ.get("EMAIL_CLEANER_DATA_DIR", _DEFAULT))
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d
