import difflib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import dns.resolver

from .domains import FREE_DOMAINS

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "mx_cache.json"
CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 días


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")


def check_syntax(email: str) -> bool:
    return bool(EMAIL_RE.match(email))


def suggest_domain_typo(domain: str):
    matches = difflib.get_close_matches(domain, FREE_DOMAINS, n=1, cutoff=0.84)
    if matches and matches[0] != domain:
        return matches[0]
    return None


def _resolve_domain(domain: str, resolver: dns.resolver.Resolver):
    """True = tiene MX (o A como fallback), False = dominio no recibe correo, None = no concluyente (timeout/error transitorio)."""
    try:
        answers = resolver.resolve(domain, "MX")
        return len(answers) > 0
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        try:
            resolver.resolve(domain, "A")
            return True
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return False
        except Exception:
            return None
    except Exception:
        return None


def resolve_mx_bulk(domains: set, max_workers: int = 30, progress_callback=None) -> dict:
    cache = _load_cache()
    now = time.time()
    result = {}
    to_resolve = []

    for d in domains:
        cached = cache.get(d)
        if cached and (now - cached["ts"]) < CACHE_TTL_SECONDS:
            result[d] = cached["has_mx"]
        else:
            to_resolve.append(d)

    resolver = dns.resolver.Resolver()
    resolver.timeout = 3
    resolver.lifetime = 5

    done = 0
    total = len(to_resolve)
    if progress_callback:
        progress_callback(done, total)

    if to_resolve:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_resolve_domain, d, resolver): d for d in to_resolve}
            for future in as_completed(futures):
                d = futures[future]
                has_mx = future.result()
                result[d] = has_mx
                if has_mx is not None:
                    cache[d] = {"has_mx": has_mx, "ts": now}
                done += 1
                if progress_callback:
                    progress_callback(done, total)

    _save_cache(cache)
    return result
