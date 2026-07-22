"""Verificación SMTP opt-in con salvaguardas y optimizada.

Hace un handshake sin enviar correo (EHLO -> MAIL FROM -> RCPT TO) contra el
servidor de destino. Optimizaciones:

- Una sola conexión por dominio: se saluda y se declara MAIL FROM una vez, y se
  hacen varios RCPT TO seguidos para todos los buzones de ese dominio.
- Paralelización por dominio (pool de hilos): varios dominios a la vez, pero un
  solo hilo por dominio (no se golpea el mismo servidor en paralelo).
- Caché de MX y de catch-all a nivel de módulo: persiste ENTRE TANDAS mientras el
  proceso siga vivo, para no re-resolver ni re-sondear lo ya visto.

ADVERTENCIA: úsalo desde un dominio/IP remitente dedicado, no desde el dominio
principal de envío, y donde el puerto 25 esté abierto.
"""
import smtplib
import socket
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import dns.resolver

# Local part improbable de existir, para detectar catch-all.
CATCHALL_PROBE = "no-existe-zzq7x1k9w3-checker"

MAX_ROWS = 3000        # tope duro de seguridad por lote
DEFAULT_WORKERS = 10   # dominios en paralelo

# Cachés a nivel de módulo: se comparten entre llamadas (tandas) del mismo proceso.
_MX_CACHE = {}         # dominio -> host MX (o None)
_CATCHALL_CACHE = {}   # dominio -> bool


def clear_caches() -> None:
    _MX_CACHE.clear()
    _CATCHALL_CACHE.clear()


def _get_mx_host(domain: str):
    if domain in _MX_CACHE:
        return _MX_CACHE[domain]
    try:
        answers = dns.resolver.resolve(domain, "MX")
        host = str(min(answers, key=lambda r: r.preference).exchange).rstrip(".")
    except Exception:
        host = None
    _MX_CACHE[domain] = host
    return host


def _classify(code):
    if code is None:
        return {"smtp_estado": "no_verificable", "smtp_detalle": "sin respuesta"}
    if 200 <= code < 300:
        return {"smtp_estado": "existe", "smtp_detalle": f"code {code}"}
    if code in (550, 551, 553):
        return {"smtp_estado": "no_existe", "smtp_detalle": f"code {code}"}
    return {"smtp_estado": "no_verificable", "smtp_detalle": f"code {code}"}


def _verify_domain(domain: str, addresses, sender: str, helo_host: str) -> dict:
    """Verifica todos los correos de un dominio reutilizando UNA conexión."""
    mx = _get_mx_host(domain)
    if not mx:
        return {a: {"smtp_estado": "sin_mx", "smtp_detalle": "no hay MX"} for a in addresses}

    # Si ya sabemos que es catch-all, no hace falta ni conectar.
    if _CATCHALL_CACHE.get(domain) is True:
        return {a: {"smtp_estado": "catch_all", "smtp_detalle": "dominio acepta todo"} for a in addresses}

    results = {}
    server = None
    try:
        server = smtplib.SMTP(timeout=10)
        server.connect(mx, 25)
        server.helo(helo_host)
        server.mail(sender)

        # Detección de catch-all (con caché).
        if domain not in _CATCHALL_CACHE:
            try:
                code, _ = server.rcpt(f"{CATCHALL_PROBE}@{domain}")
                _CATCHALL_CACHE[domain] = code is not None and 200 <= code < 300
            except (smtplib.SMTPException, socket.error):
                _CATCHALL_CACHE[domain] = False
        if _CATCHALL_CACHE.get(domain):
            server.quit()
            return {a: {"smtp_estado": "catch_all", "smtp_detalle": "dominio acepta todo"} for a in addresses}

        for a in addresses:
            try:
                code, _ = server.rcpt(a)
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPException, socket.error):
                code = None
            results[a] = _classify(code)
        server.quit()
    except (smtplib.SMTPException, socket.error, OSError):
        for a in addresses:
            results.setdefault(a, {"smtp_estado": "no_verificable", "smtp_detalle": "conexión fallida"})
        try:
            if server is not None:
                server.quit()
        except Exception:
            pass
    return results


def verify_batch(emails, sender: str, helo_host: str = None,
                 max_workers: int = DEFAULT_WORKERS, progress_callback=None) -> list:
    """Verifica una lista de correos. Devuelve resultados en el mismo orden."""
    if len(emails) > MAX_ROWS:
        raise ValueError(
            f"Lote de {len(emails)} supera el tope de {MAX_ROWS}. "
            "La verificación SMTP es solo para lotes chicos."
        )
    if not sender or "@" not in sender:
        raise ValueError("Se requiere un email remitente válido (MAIL FROM).")
    helo_host = helo_host or sender.split("@", 1)[1]

    order = [str(e).strip().lower() for e in emails]
    by_domain = defaultdict(list)
    for e in order:
        if "@" in e:
            by_domain[e.split("@", 1)[1]].append(e)

    all_results = {}
    done = 0
    total = len(order)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_verify_domain, d, addrs, sender, helo_host): d
            for d, addrs in by_domain.items()
        }
        for fut in as_completed(futures):
            all_results.update(fut.result())
            done = len(all_results)
            if progress_callback:
                progress_callback(min(done, total), total)

    return [
        all_results.get(e, {"smtp_estado": "no_verificable", "smtp_detalle": "sin resultado"})
        for e in order
    ]
