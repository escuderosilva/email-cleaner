from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_disposable_domains() -> set:
    path = DATA_DIR / "disposable_domains.txt"
    with open(path, encoding="utf-8") as f:
        return {line.strip().lower() for line in f if line.strip() and not line.startswith("#")}


FREE_DOMAINS = {
    "gmail.com", "hotmail.com", "hotmail.es", "outlook.com", "outlook.es",
    "yahoo.com", "yahoo.es", "live.com", "icloud.com", "aol.com",
    "protonmail.com", "msn.com", "gmx.com", "mail.com", "yandex.com",
    "zoho.com", "me.com",
}

ROLE_PREFIXES = {
    "info", "admin", "administracion", "administracion", "contacto", "contact",
    "ventas", "sales", "soporte", "support", "hola", "hello", "marketing",
    "rrhh", "hr", "compras", "gerencia", "facturacion", "billing", "no-reply",
    "noreply", "no_reply", "webmaster", "postmaster", "office", "oficina",
    "recepcion", "reception", "cotizaciones", "pedidos", "orders", "cobranza",
    "cobranzas", "pagos", "tesoreria", "finanzas", "operaciones", "logistica",
    "servicioalcliente", "atencionalcliente", "clientes", "comercial",
    "gerenciageneral", "gerente", "jefatura", "secretaria", "asistente",
    "correo", "mail", "contact-us", "enquiries", "hello", "team", "equipo",
}

# Prefijos que casi siempre indican buzones no aptos para marketing / spam traps.
SUSPICIOUS_LOCAL_PARTS = {
    "abuse", "spam", "postmaster", "hostmaster", "root", "nobody",
    "mailer-daemon", "test", "prueba", "asdf", "example", "ejemplo",
    "donotreply", "do-not-reply",
}

DISPOSABLE_DOMAINS = load_disposable_domains()
