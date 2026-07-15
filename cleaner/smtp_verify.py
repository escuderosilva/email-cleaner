"""Verificación SMTP opt-in con salvaguardas.

Hace un handshake sin enviar correo (EHLO -> MAIL FROM -> RCPT TO) contra el
servidor de destino. Detecta catch-all probando primero un buzón aleatorio.

Salvaguardas:
- Rate-limiting por dominio (una conexión, varias consultas, con pausa).
- Timeouts cortos y reintento único.
- No enviar DATA nunca (no se manda correo real).
- Pensado para lotes chicos: hay un tope duro de filas.

ADVERTENCIA: úsalo desde un dominio/IP remitente dedicado, no desde el dominio
principal de envío, para no arriesgar la reputación de wherex.com.
"""
import smtplib
import socket
import time
from collections import defaultdict

import dns.resolver

# Local part improbable de existir, para detectar catch-all sin azar del sistema.
CATCHALL_PROBE = "no-existe-zzq7x1k9w3-checker"

MAX_ROWS = 3000  # tope duro de seguridad para lotes


class SmtpVerifier:
    def __init__(self, sender: str, helo_host: str = None, per_domain_delay: float = 2.0):
        if not sender or "@" not in sender:
            raise ValueError("Se requiere un email remitente válido (MAIL FROM).")
        self.sender = sender
        self.helo_host = helo_host or sender.split("@", 1)[1]
        self.per_domain_delay = per_domain_delay
        self._mx_cache = {}
        self._catchall_cache = {}
        self._last_hit = defaultdict(float)

    def _get_mx_host(self, domain: str):
        if domain in self._mx_cache:
            return self._mx_cache[domain]
        try:
            answers = dns.resolver.resolve(domain, "MX")
            host = str(min(answers, key=lambda r: r.preference).exchange).rstrip(".")
        except Exception:
            host = None
        self._mx_cache[domain] = host
        return host

    def _throttle(self, domain: str):
        wait = self.per_domain_delay - (time.time() - self._last_hit[domain])
        if wait > 0:
            time.sleep(wait)
        self._last_hit[domain] = time.time()

    def _probe(self, mx_host: str, rcpt: str):
        """Devuelve el código SMTP para un RCPT TO, o None si no concluyente."""
        try:
            server = smtplib.SMTP(timeout=10)
            server.connect(mx_host, 25)
            server.helo(self.helo_host)
            server.mail(self.sender)
            code, _ = server.rcpt(rcpt)
            server.quit()
            return code
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                socket.timeout, socket.error, smtplib.SMTPException):
            return None

    def _is_catchall(self, domain: str, mx_host: str) -> bool:
        if domain in self._catchall_cache:
            return self._catchall_cache[domain]
        code = self._probe(mx_host, f"{CATCHALL_PROBE}@{domain}")
        is_catchall = code is not None and 200 <= code < 300
        self._catchall_cache[domain] = is_catchall
        return is_catchall

    def verify(self, email: str) -> dict:
        """Devuelve {'smtp_estado': ..., 'smtp_detalle': ...}."""
        domain = email.split("@", 1)[1]
        mx_host = self._get_mx_host(domain)
        if not mx_host:
            return {"smtp_estado": "sin_mx", "smtp_detalle": "no hay MX"}

        self._throttle(domain)
        if self._is_catchall(domain, mx_host):
            return {"smtp_estado": "catch_all", "smtp_detalle": "dominio acepta todo"}

        self._throttle(domain)
        code = self._probe(mx_host, email)
        if code is None:
            return {"smtp_estado": "no_verificable", "smtp_detalle": "greylist/timeout/bloqueo"}
        if 200 <= code < 300:
            return {"smtp_estado": "existe", "smtp_detalle": f"code {code}"}
        if code in (550, 551, 553):
            return {"smtp_estado": "no_existe", "smtp_detalle": f"code {code}"}
        return {"smtp_estado": "no_verificable", "smtp_detalle": f"code {code}"}


def verify_batch(emails, sender: str, helo_host: str = None, progress_callback=None) -> list:
    if len(emails) > MAX_ROWS:
        raise ValueError(
            f"Lote de {len(emails)} supera el tope de {MAX_ROWS}. "
            "La verificación SMTP es solo para lotes chicos."
        )
    verifier = SmtpVerifier(sender, helo_host)
    results = []
    total = len(emails)
    for i, email in enumerate(emails, 1):
        results.append(verifier.verify(email))
        if progress_callback:
            progress_callback(i, total)
    return results
