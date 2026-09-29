# src/utils.py
import requests

def get_country_from_ip(ip_address):
    """Détermine le pays d'origine d'une adresse IP via une API externe."""
    if ip_address in ("127.0.0.1", "localhost", "::1") or ip_address.startswith("192.168."):
        return "Local Network"
    try:
        response = requests.get(f"https://ipapi.co/{ip_address}/json/", timeout=3)
        if response.status_code == 200:
            return response.json().get("country_name", "Unknown")
    except Exception:
        pass
    return "Unknown"