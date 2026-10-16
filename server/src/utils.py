import ipaddress
import logging
import threading
import time

import requests

COUNTRY_CACHE_TTL = 24 * 60 * 60
UNKNOWN_CACHE_TTL = 5 * 60
COUNTRY_CACHE_LIMIT = 4096
_country_cache = {}
_country_lookups = {}
_country_cache_lock = threading.Lock()
logger = logging.getLogger(__name__)


def get_country_from_ip(ip_address):
    """Determine an IP address's country, caching results to limit external requests."""
    try:
        parsed_ip = ipaddress.ip_address(ip_address)
    except ValueError:
        return "Unknown"

    if not parsed_ip.is_global:
        return "Local Network"

    cache_key = str(parsed_ip)
    now = time.monotonic()
    with _country_cache_lock:
        cached = _country_cache.get(cache_key)
        if cached and cached[1] > now:
            return cached[0]
        lookup_event = _country_lookups.get(cache_key)
        should_lookup = lookup_event is None
        if should_lookup:
            lookup_event = threading.Event()
            _country_lookups[cache_key] = lookup_event

    if not should_lookup:
        lookup_event.wait(timeout=6)
        with _country_cache_lock:
            cached = _country_cache.get(cache_key)
            return cached[0] if cached and cached[1] > time.monotonic() else "Unknown"

    country = "Unknown"
    try:
        response = requests.get(
            f"https://ipapi.co/{parsed_ip}/json/",
            timeout=(2, 3)
        )
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("country_name"), str):
                country = payload["country_name"].strip() or "Unknown"
        else:
            logger.warning(
                "Géolocalisation indisponible pour %s (HTTP %s)",
                parsed_ip,
                response.status_code
            )
    except (requests.RequestException, ValueError) as error:
        logger.warning("Échec de la géolocalisation pour %s : %s", parsed_ip, error)

    finally:
        ttl = COUNTRY_CACHE_TTL if country != "Unknown" else UNKNOWN_CACHE_TTL
        with _country_cache_lock:
            if len(_country_cache) >= COUNTRY_CACHE_LIMIT:
                expired_keys = [
                    key for key, (_, expires_at) in _country_cache.items()
                    if expires_at <= time.monotonic()
                ]
                for key in expired_keys:
                    _country_cache.pop(key, None)
                if len(_country_cache) >= COUNTRY_CACHE_LIMIT:
                    _country_cache.pop(next(iter(_country_cache)))
            _country_cache[cache_key] = (country, time.monotonic() + ttl)
            _country_lookups.pop(cache_key, None)
            lookup_event.set()

    return country
