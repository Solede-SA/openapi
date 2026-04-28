"""
Wrapper per il servizio Geocoder di OpenAPI.

Riproduce il pattern di apps/openapi/openapi/api/aziende/company_start.py:
- Authorization Bearer dal token Company.custom_open_api_token
- URL via openapi.tools.common_data.get_service("Geocoder", endpoint)
- Cache Frappe per query ripetute (TTL 7 giorni)
- log_error + return dict {"error": ...} su eccezioni

Risposta normalizzata:
{
  "success": bool,
  "lat": float | None, "lon": float | None,
  "confidence": float | None,           # 0..1
  "place_type": str | None,             # "premise"/"street"/"stairs"/"square"/...
  "formatted_address": str | None,
  "city": str | None, "pincode": str | None, "state": str | None, "country": str | None,
  "raw": dict,
  "error": str | None,
}
"""

import hashlib

import frappe
import requests

import openapi.tools.common_data as common_data


CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 giorni


def _get_company_token():
    company_name = frappe.defaults.get_global_default("company")
    if not company_name:
        return None
    return frappe.db.get_value("Company", company_name, "custom_open_api_token")


def _normalize_response(payload):
    """
    Mappa la risposta OpenAPI Geocoder allo schema interno.
    Formato OpenAPI: {"element": {...}, "success": bool, "message": str, "error": null}.
    L'element contiene latitude, longitude, streetNumber, streetName, postalCode,
    locality, country, countryCode, adminLevels (1=regione, 2=provincia, 3=comune).
    """
    base = {
        "success": False,
        "lat": None, "lon": None,
        "street_number": None, "street_name": None,
        "formatted_address": None,
        "city": None, "pincode": None, "state": None, "country": None,
        "raw": payload,
        "error": None,
    }
    if not isinstance(payload, dict):
        return {**base, "error": "Risposta geocoder non valida (non dict)"}

    if not payload.get("success", True):
        return {**base, "error": payload.get("message") or "Errore geocoder"}

    element = payload.get("element")
    if not isinstance(element, dict):
        return {**base, "error": "Geocoder: nessun risultato"}

    lat = element.get("latitude")
    lon = element.get("longitude")
    admin_levels = element.get("adminLevels") or {}
    province = ""
    province_node = admin_levels.get("2") if isinstance(admin_levels, dict) else None
    if isinstance(province_node, dict):
        province = province_node.get("code") or province_node.get("name") or ""

    street_number = element.get("streetNumber") or ""
    street_name = element.get("streetName") or ""
    formatted = ", ".join(filter(None, [
        f"{street_name} {street_number}".strip(),
        f"{element.get('postalCode') or ''} {element.get('locality') or ''}".strip(),
        province,
        element.get("country") or "",
    ]))

    return {
        "success": lat is not None and lon is not None,
        "lat": float(lat) if lat is not None else None,
        "lon": float(lon) if lon is not None else None,
        "street_number": street_number,
        "street_name": street_name,
        "formatted_address": formatted,
        "city": element.get("locality") or "",
        "pincode": element.get("postalCode") or "",
        "state": province,
        "country": element.get("countryCode") or element.get("country") or "",
        "raw": payload,
        "error": None,
    }


@frappe.whitelist()
def geocode_address(query):
    """
    Geocodifica un indirizzo in formato libero ("via X 12, 20100 Milano (MI), Italy").
    Ritorna un dict normalizzato (vedi modulo docstring). In caso di errore tecnico
    restituisce {"error": "..."} con campi geografici nulli.
    """
    if not query or not query.strip():
        return {"error": "query vuota", "success": False}
    query = query.strip()

    cache_key = f"openapi|geocode|{hashlib.sha256(query.encode('utf-8')).hexdigest()}"
    cached = frappe.cache.get_value(cache_key)
    if cached is not None:
        return cached

    token = _get_company_token()
    if not token:
        return {"error": "Token OpenAPI non configurato sulla Company", "success": False}

    try:
        url = common_data.get_service("Geocoder", "geocode")
    except Exception as e:
        frappe.log_error(f"OpenApi Service 'Geocoder' non configurato: {e}", "openapi.geocode")
        return {"error": "Servizio 'Geocoder' non configurato in OpenApi Services", "success": False}

    # Il token Company.custom_open_api_token include gia' il prefisso "Bearer "
    # (cfr. apps/openapi/openapi/api/aziende/company_start.py)
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(url, headers=headers, json={"address": query}, timeout=10)
        if response.status_code != 200:
            details = None
            try:
                details = response.json()
            except Exception:
                details = response.text[:500]
            frappe.log_error(
                f"Geocoder HTTP {response.status_code}: {details}",
                "openapi.geocode",
            )
            return {"error": f"Geocoder HTTP {response.status_code}", "details": details, "success": False}
        normalized = _normalize_response(response.json())
        # Salva in cache solo le risposte valide
        if normalized.get("success"):
            frappe.cache.set_value(cache_key, normalized, expires_in_sec=CACHE_TTL_SECONDS)
        return normalized
    except requests.RequestException as e:
        frappe.log_error(f"Geocoder request error: {e}", "openapi.geocode")
        return {"error": str(e), "success": False}
