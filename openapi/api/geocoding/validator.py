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


# Toponimi nel nome della via che indicano luoghi pubblici / non commerciali.
# Heuristica testuale leggera (l'API OpenAPI Geocoder non ritorna un place_type).
NON_COMMERCIAL_TOKENS = (
    "scala", "scalea", "scalinata", "piazzale", "piazza", "vicolo", "salita",
    "ponte", "rotonda", "rotatoria", "parco", "giardini", "lungomare", "molo",
)

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

    if geo.get("pending"):
        warnings.append("Geocodifica in corso — risalva o premi «Aggiorna geocoder» tra qualche istante")
        return warnings

    if not geo.get("success"):
        warnings.append(f"Indirizzo non riconosciuto dal geocoder ({geo.get('error') or 'no result'})")
        return warnings

    # Numero civico non risolto dal geocoder (ambiguità in input)
    if not (geo.get("street_number") or "").strip():
        warnings.append("Numero civico non risolto dal geocoder (indirizzo ambiguo o senza civico)")

    # Toponimo non idoneo (scalea, piazzale, scalinata, ...)
    street_name = (geo.get("street_name") or "").lower()
    line1_lower = line1.lower()
    for tok in NON_COMMERCIAL_TOKENS:
        if tok in street_name or tok in line1_lower:
            warnings.append(f"Toponimo non idoneo per attività ('{tok}' nel nome via)")
            break

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

    geo_state = (geo.get("state") or "").strip().upper()
    addr_state = (addr.get("state") or "").strip().upper()
    if geo_state and addr_state and geo_state != addr_state:
        warnings.append(
            f"Provincia inserita ({addr_state}) non corrisponde a quella riconosciuta ({geo_state})"
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
        address_doc.geocode_confidence = None  # API OpenAPI Geocoder non espone confidence
        address_doc.geocode_place_type = geo.get("street_name") or ""
        address_doc.geocode_formatted_address = geo.get("formatted_address") or ""
        address_doc.geocode_status = "Warning" if warnings else "OK"
    else:
        address_doc.geocode_latitude = None
        address_doc.geocode_longitude = None
        address_doc.geocode_confidence = None
        address_doc.geocode_place_type = ""
        address_doc.geocode_formatted_address = ""
        # "pending": sourcing async non ancora completato dopo i retry — stato transitorio,
        # non un errore (si risolve al salvataggio/refresh successivo).
        address_doc.geocode_status = "Pending" if geo.get("pending") else "Error"

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


# Mappa Address.field -> chiave nel dict normalizzato dal geocoder + label umana
_SUGGESTION_FIELDS = [
    ("address_line1", "_recognized_line1", "Indirizzo (via + civico)"),
    ("city", "city", "Città"),
    ("pincode", "pincode", "CAP"),
    ("state", "state", "Provincia"),
]


def _build_recognized_line1(geo: dict) -> str:
    name = (geo.get("street_name") or "").strip()
    num = (geo.get("street_number") or "").strip()
    return f"{name} {num}".strip() if num else name


@frappe.whitelist()
def get_geocode_suggestions(address_name):
    """
    Ritorna i diff tra i campi Address correnti e quelli riconosciuti dal
    geocoder (parsando geocode_payload). Nessuna chiamata API, solo lettura.
    """
    import json
    addr = frappe.get_doc("Address", address_name)
    raw = addr.get("geocode_payload") or ""
    if not raw:
        return {"available": False, "differences": []}
    try:
        # geocode_payload e' gia' il dict normalizzato (post _normalize_response)
        geo = json.loads(raw)
    except Exception:
        return {"available": False, "differences": []}

    if not geo.get("success"):
        return {"available": False, "differences": []}

    geo["_recognized_line1"] = _build_recognized_line1(geo)

    diffs = []
    for field, geo_key, label in _SUGGESTION_FIELDS:
        current = (addr.get(field) or "").strip()
        suggested = (geo.get(geo_key) or "").strip()
        if not suggested:
            continue
        # confronto case-insensitive per testo, exact per CAP/provincia
        equal = (
            current.lower() == suggested.lower()
            if field in ("address_line1", "city")
            else current.upper() == suggested.upper()
        )
        if not equal:
            diffs.append({
                "field": field,
                "label": label,
                "current": current,
                "suggested": suggested,
            })
    return {"available": True, "differences": diffs}


@frappe.whitelist()
def apply_geocode_suggestions(address_name, fields):
    """
    Applica le correzioni riconosciute dal geocoder ai campi specificati.

    `fields` e' una lista (o stringa JSON) di nomi-campo Address da aggiornare
    (es. ["pincode", "city"]). Per ognuno legge il valore "suggested" da
    get_geocode_suggestions e lo scrive sul doc; al save() l'hook before_save
    rigenera il geocoding (di solito porta status a OK).
    """
    import json
    if isinstance(fields, str):
        fields = json.loads(fields)
    if not isinstance(fields, list) or not fields:
        frappe.throw("Lista campi vuota")

    suggestions = get_geocode_suggestions(address_name)
    if not suggestions.get("available"):
        frappe.throw("Nessun suggerimento disponibile per questo indirizzo")
    by_field = {d["field"]: d["suggested"] for d in suggestions["differences"]}

    addr = frappe.get_doc("Address", address_name)
    applied = []
    for field in fields:
        if field in by_field:
            setattr(addr, field, by_field[field])
            applied.append(field)
    if not applied:
        frappe.throw("Nessuno dei campi richiesti ha un suggerimento")

    addr.flags.ignore_permissions = True
    addr.save()
    return {"success": True, "applied": applied, "status": addr.geocode_status}
