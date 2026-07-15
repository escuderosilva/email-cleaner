"""Refresca el caché MX para que los dominios ya conocidos no expiren.

Uso (idealmente por cron, ej. semanal):
    python scripts/refresh_mx_cache.py

Re-resuelve todos los dominios del caché y actualiza su timestamp.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleaner.validators import CACHE_PATH, resolve_mx_bulk


def main():
    if not CACHE_PATH.exists():
        print("No hay caché aún. Nada que refrescar.")
        return

    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    domains = set(cache.keys())
    print(f"Refrescando {len(domains)} dominios...")

    start = time.time()
    # Forzamos re-resolución vaciando el archivo primero.
    CACHE_PATH.write_text("{}", encoding="utf-8")
    resolve_mx_bulk(domains)
    print(f"Listo en {round(time.time() - start, 1)} s.")


if __name__ == "__main__":
    main()
