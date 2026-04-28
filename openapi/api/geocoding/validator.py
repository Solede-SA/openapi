"""
Validatore di indirizzo: combina geocoding e regole heuristiche per segnalare
anomalie (numero civico SNC, tipo luogo non commerciale, mismatch citta'/CAP, ...).

Pensato per essere agganciato a doc_events.Address.before_save in qualunque app
che usi `openapi`. La validazione e' non-bloccante: popola i campi
`geocode_*` sull'Address (status, lat/lon, warnings, ...) e l'operatore decide.
"""

import json
import re

import frappe

from openapi.api.geocoding.forward import geocode_address


# place_type ritornati dal geocoder che NON sono adatti come destinazione di
# attivita' commerciale / spedizione di un dispositivo. Lista deliberatamente
# breve: l'aggiunta di nuovi tipi richiede un ragionamento esplicito.
NON_COMMERCIAL_PLACE_TYPES = {"stairs", "square", "street", "path", "pedestrian", "footway"}

CONFIDENCE_THRESHOLD = 0.6

ADDRESS_TRIGGER_FIELDS = ("address_line1", "address_line2", "city", "pincode", "state", "country")


def _build_query(addr) -> str:
    parts = [addr.get("address_line1") or ""]
    line2 = addr.get("address_line2")
    if line2:
        parts.append(line2)
    cap_city = " ".join(filter(None, [addr.get("pincode") or "", addr.get("city") or ""]))
    if cap_city.strip():
        parts.append(cap_city.strip())
    if addr.get("state"):
        parts[-1] = f"{parts[-1]} ({addr.state})"
    if addr.get("country"):
        parts.append(addr.country)
    return ", ".join([p for p in parts if p])


def _compute_warnings(addr, geo: dict) -> list:
    warnings = []

    line1 = (addr.get("address_line1") or "").strip()
    if re.search(r"\bSNC\b", line1, re.IGNORECASE):
        warnings.append("Numero civico assente (SNC)")
    elif not re.search(r"\d", line1):
        warnings.append("Numero civico non riconoscibile in 'address_line1'")

    if not geo.get("success"):
        warnings.append(f"Indirizzo non riconosciuto dal geocoder ({geo.get('error') or 'no result'})")
        return warnings

    confidence = geo.get("confidence")
    if confidence is not None and confidence < CONFIDENCE_THRESHOLD:
        warnings.append(f"Bassa confidenza geocoder ({confidence:.2f})")

    place_type = (geo.get("place_type") or "").lower()
    if place_type and place_type in NON_COMMERCIAL_PLACE_TYPES:
        warnings.append(f"Tipo luogo non idoneo per attività: {geo.get('place_type')}")

    geo_city = (geo.get("city") or "").strip().lower()
    addr_city = (addr.get("city") or "").strip().lower()
    if geo_city and addr_city and geo_city != addr_city:
        warnings.append(
            f"Città inserita ({addr.get('city')}) non corrisponde a quella riconosciuta ({geo.get('city')})"
        )

    geo_pincode = (geo.get("pincode") or "").strip()
    addr_pincode = (addr.get("pincode") or "").strip()
    if geo_pincode and addr_pincode and geo_pincode != addr_pincode:
        warnings.append(
            f"CAP inserito ({addr_pincode}) non corrisponde a quello riconosciuto ({geo_pincode})"
        )

    return warnings


def validate_and_geocode_address(address_doc, force=False):
    """
    Esegue geocoding + validazione e popola i custom field geocode_* sul doc.
    Non chiama save: il chiamante (hook before_save) lo fa già.

    Skippa la chiamata API se nessun campo indirizzo e' cambiato e
    geocode_status e' gia' impostato (a meno di force=True).
    """
    is_new = address_doc.is_new() if hasattr(address_doc, "is_new") else not address_doc.get("name")
    address_changed = is_new or any(address_doc.has_value_changed(f) for f in ADDRESS_TRIGGER_FIELDS)
    has_status = bool(address_doc.get("geocode_status"))
    if not force and not address_changed and has_status:
        return None

    query = _build_query(address_doc)
    if not query.strip():
        address_doc.geocode_status = "Error"
        address_doc.geocode_warnings = "Indirizzo vuoto"
        address_doc.geocode_last_run = frappe.utils.now()
        return None

    geo = geocode_address(query) or {}
    warnings = _compute_warnings(address_doc, geo)

    if geo.get("success"):
        address_doc.geocode_latitude = geo.get("lat")
        address_doc.geocode_longitude = geo.get("lon")
        address_doc.geocode_confidence = geo.get("confidence")
        address_doc.geocode_place_type = geo.get("place_type") or ""
        address_doc.geocode_formatted_address = geo.get("formatted_address") or ""
        address_doc.geocode_status = "Warning" if warnings else "OK"
    else:
        address_doc.geocode_latitude = None
        address_doc.geocode_longitude = None
        address_doc.geocode_confidence = None
        address_doc.geocode_place_type = ""
        address_doc.geocode_formatted_address = ""
        address_doc.geocode_status = "Error"

    address_doc.geocode_warnings = "\n".join(f"• {w}" for w in warnings) if warnings else ""
    address_doc.geocode_last_run = frappe.utils.now()
    address_doc.geocode_payload = json.dumps(geo, ensure_ascii=False, default=str)
    return geo


def validate_and_geocode_address_hook(doc, method=None):
    """Hook compatibile con doc_events.Address.before_save."""
    try:
        validate_and_geocode_address(doc, force=False)
    except Exception as e:
        # Non blocca il save: logga e setta status Error
        frappe.log_error(f"Geocode hook error on {doc.name}: {e}", "openapi.geocode.hook")
        doc.geocode_status = "Error"
        doc.geocode_warnings = f"Errore geocoder: {e}"
        doc.geocode_last_run = frappe.utils.now()


@frappe.whitelist()
def refresh_address_geocode(address_name):
    """Riapplica il geocoding su un Address esistente, anche se i campi non sono cambiati."""
    addr = frappe.get_doc("Address", address_name)
    validate_and_geocode_address(addr, force=True)
    addr.flags.ignore_permissions = True
    addr.save()
    return {"success": True, "status": addr.geocode_status, "warnings": addr.geocode_warnings or ""}
