"""
Crea i Custom Field per il geocoding sull'`Address` standard di Frappe.

Idempotente: aggiunge solo i field mancanti. Tutti con `module="Openapi"` cosi'
vengono esportati nei fixture dell'app `openapi`.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


GEOCODE_STATUS_OPTIONS = "\n".join(["", "Pending", "OK", "Warning", "Error"])


def execute():
    custom_fields = {
        "Address": [
            {
                "fieldname": "geocode_section",
                "label": "Geocoding",
                "fieldtype": "Section Break",
                "insert_after": "links",
                "collapsible": 1,
                "module": "Openapi",
            },
            {
                "fieldname": "geocode_status",
                "label": "Geocoding Status",
                "fieldtype": "Select",
                "options": GEOCODE_STATUS_OPTIONS,
                "read_only": 1,
                "in_list_view": 1,
                "insert_after": "geocode_section",
                "module": "Openapi",
            },
            {
                "fieldname": "geocode_warnings",
                "label": "Anomalie rilevate",
                "fieldtype": "Small Text",
                "read_only": 1,
                "depends_on": "eval:doc.geocode_warnings",
                "insert_after": "geocode_status",
                "module": "Openapi",
            },
            {
                "fieldname": "geocode_formatted_address",
                "label": "Indirizzo riconosciuto",
                "fieldtype": "Small Text",
                "read_only": 1,
                "insert_after": "geocode_warnings",
                "module": "Openapi",
            },
            {
                "fieldname": "geocode_col_break",
                "fieldtype": "Column Break",
                "insert_after": "geocode_formatted_address",
                "module": "Openapi",
            },
            {
                "fieldname": "geocode_latitude",
                "label": "Latitudine",
                "fieldtype": "Float",
                "precision": "7",
                "read_only": 1,
                "insert_after": "geocode_col_break",
                "module": "Openapi",
            },
            {
                "fieldname": "geocode_longitude",
                "label": "Longitudine",
                "fieldtype": "Float",
                "precision": "7",
                "read_only": 1,
                "insert_after": "geocode_latitude",
                "module": "Openapi",
            },
            {
                "fieldname": "geocode_confidence",
                "label": "Confidenza geocoder",
                "fieldtype": "Float",
                "precision": "2",
                "read_only": 1,
                "insert_after": "geocode_longitude",
                "module": "Openapi",
            },
            {
                "fieldname": "geocode_place_type",
                "label": "Tipo luogo",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "geocode_confidence",
                "module": "Openapi",
            },
            {
                "fieldname": "geocode_last_run",
                "label": "Ultimo geocoding",
                "fieldtype": "Datetime",
                "read_only": 1,
                "insert_after": "geocode_place_type",
                "module": "Openapi",
            },
            {
                "fieldname": "geocode_payload",
                "label": "Geocoder payload (debug)",
                "fieldtype": "Long Text",
                "read_only": 1,
                "hidden": 1,
                "insert_after": "geocode_last_run",
                "module": "Openapi",
            },
        ]
    }
    create_custom_fields(custom_fields, ignore_validate=True, update=True)
    frappe.db.commit()
