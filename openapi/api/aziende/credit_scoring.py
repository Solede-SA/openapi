# Copyright (c) 2025, OpenAPI and contributors
# For license information, please see license.txt

import frappe
import json
import requests
import openapi.tools.common_data as common_data


def get_company_doc():
    return frappe.get_doc("Company", frappe.defaults.get_global_default("company"))


@frappe.whitelist()
def get_credit_score(vat_or_tax_code):
    """
    Recupera il credit score di un'azienda tramite OpenAPI Credit Scoring Advanced.

    Args:
        vat_or_tax_code: Partita IVA o Codice Fiscale dell'azienda

    Returns:
        dict con rating, risk_score, operational_credit_limit, etc.
    """
    if not vat_or_tax_code:
        return {"error": "Inserire partita IVA o codice fiscale"}

    # Pulisci l'input
    vat_or_tax_code = vat_or_tax_code.strip().replace(" ", "").replace("-", "")

    # Cache per evitare chiamate ripetute
    chiave_cache = f"openapi|credit_score|{vat_or_tax_code}"
    risultato_cache = frappe.cache.get_value(chiave_cache)
    if risultato_cache is not None:
        return risultato_cache

    url = common_data.get_service("Credit Scoring Advanced", f"IT-creditscore-advanced/{vat_or_tax_code}")
    company = get_company_doc()

    if not company.custom_open_api_token:
        return {"error": "Token OpenAPI non configurato"}

    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            response_data = response.json()

            if response_data.get("success") and response_data.get("data"):
                data = response_data["data"]
                # Cache per 24 ore (il credit score non cambia frequentemente)
                frappe.cache.set_value(chiave_cache, data, expires_in_sec=86400)
                return data
            else:
                return {
                    "error": response_data.get("message", "Errore sconosciuto"),
                    "details": response_data,
                }
        elif response.status_code == 406:
            response_json = response.json()
            return {
                "error": f"Partita IVA non valida: {response_json.get('message', '')}",
                "details": response_json,
            }
        else:
            response_json = response.json()
            return {
                "error": f"Errore API: {response.status_code}",
                "details": response_json,
            }
    except Exception as e:
        return {"error": str(e)}


@frappe.whitelist()
def get_customer_credit_score(customer_name):
    """
    Recupera il credit score di un cliente esistente.

    Args:
        customer_name: Nome del documento Customer

    Returns:
        dict con i dati del credit score
    """
    customer = frappe.get_doc("Customer", customer_name)

    if customer.customer_type != "Company":
        return {"error": "La verifica creditizia è disponibile solo per clienti di tipo Azienda"}

    if not customer.tax_id:
        return {"error": "Il cliente non ha partita IVA/codice fiscale"}

    return get_credit_score(customer.tax_id)


@frappe.whitelist()
def save_credit_score_to_customer(customer_name, credit_data):
    """
    Salva i dati del credit score nei custom fields del cliente.

    Args:
        customer_name: Nome del documento Customer
        credit_data: Dati del credit score da salvare
    """
    if isinstance(credit_data, str):
        credit_data = json.loads(credit_data)

    customer = frappe.get_doc("Customer", customer_name)

    # Aggiorna i custom fields
    if "rating" in credit_data:
        customer.custom_credit_rating = credit_data.get("rating")

    if "risk_score" in credit_data:
        customer.custom_credit_risk_score = credit_data.get("risk_score")

    if "risk_score_description" in credit_data:
        customer.custom_credit_risk_description = credit_data.get("risk_score_description")

    if "operational_credit_limit" in credit_data:
        customer.custom_credit_limit = credit_data.get("operational_credit_limit")

    if "risk_severity" in credit_data:
        customer.custom_credit_risk_severity = credit_data.get("risk_severity")

    # Salva la data dell'ultima verifica
    customer.custom_credit_score_date = frappe.utils.now()

    customer.save()

    return {"success": True, "message": "Dati credit score salvati con successo"}
