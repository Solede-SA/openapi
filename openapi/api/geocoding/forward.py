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
    OpenAPI ritorna tipicamente {"success": true, "data": [...]} con feature GeoJSON.
    Tolleriamo formati diversi cercando i campi tipici.
    """
    if not isinstance(payload, dict):
        return {"success": False, "error": "Risposta geocoder non valida (non dict)", "raw": payload}

    if not payload.get("success", True):
        return {
            "success": False,
            "error": payload.get("message") or "Errore geocoder",
            "raw": payload,
            "lat": None, "lon": None, "confidence": None, "place_type": None,
            "formatted_address": None, "city": None, "pincode": None, "state": None, "country": None,
        }

    data = payload.get("data")
    feature = None
    if isinstance(data, list) and data:
        feature = data[0]
    elif isinstance(data, dict):
        feature = data
    else:
        feature = payload  # alcuni servizi mettono i campi direttamente al top-level

    if not isinstance(feature, dict):
        return {
            "success": False, "error": "Geocoder: nessun risultato",
            "raw": payload,
            "lat": None, "lon": None, "confidence": None, "place_type": None,
            "formatted_address": None, "city": None, "pincode": None, "state": None, "country": None,
        }

    # Estrai lat/lon (formati GeoJSON o flat)
    lat = lon = None
    geometry = feature.get("geometry") or {}
    coords = geometry.get("coordinates")
    if isinstance(coords, list) and len(coords) >= 2:
        lon, lat = coords[0], coords[1]
    else:
        lat = feature.get("lat") or feature.get("latitude")
        lon = feature.get("lon") or feature.get("lng") or feature.get("longitude")

    properties = feature.get("properties") or feature

    return {
        "success": lat is not None and lon is not None,
        "lat": float(lat) if lat is not None else None,
        "lon": float(lon) if lon is not None else None,
        "confidence": properties.get("confidence") or properties.get("relevance"),
        "place_type": properties.get("type") or properties.get("place_type") or properties.get("category"),
        "formatted_address": properties.get("formatted") or properties.get("display_name") or properties.get("label"),
        "city": properties.get("city") or properties.get("town") or properties.get("locality"),
        "pincode": properties.get("postcode") or properties.get("postal_code") or properties.get("zip"),
        "state": properties.get("state") or properties.get("province") or properties.get("region"),
        "country": properties.get("country"),
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
    }

    try:
        response = requests.get(url, headers=headers, params={"address": query}, timeout=10)
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
