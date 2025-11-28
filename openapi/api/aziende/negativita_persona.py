# Copyright (c) 2025, OpenAPI and contributors
# For license information, please see license.txt

import frappe
import json
import requests
import openapi.tools.common_data as common_data


def get_company_doc():
    return frappe.get_doc("Company", frappe.defaults.get_global_default("company"))


def get_callback_url():
    """Genera l'URL di callback per ricevere i risultati"""
    site_url = frappe.utils.get_url()
    return f"{site_url}/api/method/openapi.api.aziende.negativita_persona.handle_callback"


@frappe.whitelist()
def request_negativita_check(fiscal_code, customer_name=None):
    """
    Invia richiesta di verifica negatività per persona fisica.

    Args:
        fiscal_code: Codice fiscale della persona
        customer_name: Nome del Customer (opzionale, per salvare il request_id)

    Returns:
        dict con request_id e status
    """
    if not fiscal_code:
        return {"error": "Inserire codice fiscale"}

    # Pulisci l'input
    fiscal_code = fiscal_code.strip().upper().replace(" ", "")

    # Valida formato codice fiscale (16 caratteri alfanumerici)
    if len(fiscal_code) != 16:
        return {"error": "Il codice fiscale deve essere di 16 caratteri"}

    url = common_data.get_service("Negativita Persona", "IT-negativita")
    company = get_company_doc()

    if not company.custom_open_api_token:
        return {"error": "Token OpenAPI non configurato"}

    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }

    # Prepara payload con callback
    payload = {
        "cf_piva": fiscal_code,
        "callback": {
            "url": get_callback_url(),
            "method": "POST",
            "headers": {
                "Content-Type": "application/json"
            }
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code in [200, 201, 202]:
            response_data = response.json()

            if response_data.get("success"):
                data = response_data.get("data", {})
                request_id = data.get("id")

                # Salva request_id nel Customer se specificato
                if customer_name and request_id:
                    frappe.db.set_value("Customer", customer_name,
                                       "custom_negativita_request_id", request_id)
                    frappe.db.set_value("Customer", customer_name,
                                       "custom_negativita_status", "In Elaborazione")
                    frappe.db.set_value("Customer", customer_name,
                                       "custom_negativita_request_date", frappe.utils.now())
                    frappe.db.commit()

                return {
                    "success": True,
                    "request_id": request_id,
                    "status": data.get("status", "PENDING"),
                    "message": "Richiesta inviata. Riceverai i risultati via callback o usa 'Controlla Stato'."
                }
            else:
                return {
                    "error": response_data.get("message", "Errore sconosciuto"),
                    "details": response_data
                }
        else:
            response_json = response.json() if response.text else {}
            return {
                "error": f"Errore API: {response.status_code}",
                "details": response_json
            }
    except Exception as e:
        return {"error": str(e)}


@frappe.whitelist()
def check_request_status(request_id, customer_name=None):
    """
    Controlla lo stato di una richiesta di verifica negatività.

    Args:
        request_id: ID della richiesta
        customer_name: Nome del Customer (opzionale, per aggiornare lo stato)

    Returns:
        dict con status e dati se completata
    """
    if not request_id:
        return {"error": "Request ID mancante"}

    url = common_data.get_service("Negativita Persona", f"IT-richiesta/{request_id}")
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

            if response_data.get("success"):
                data = response_data.get("data", {})
                status = data.get("status", "PENDING")

                # Aggiorna status nel Customer se specificato
                if customer_name:
                    status_label = "Completata" if status == "COMPLETED" else "In Elaborazione"
                    frappe.db.set_value("Customer", customer_name,
                                       "custom_negativita_status", status_label)
                    frappe.db.commit()

                result = {
                    "success": True,
                    "status": status,
                    "data": data
                }

                # Se completata, ottieni anche i dettagli
                if status == "COMPLETED":
                    details = get_negativita_details(request_id)
                    if details.get("success"):
                        result["details"] = details.get("data")

                        # Salva risultati nel Customer
                        if customer_name:
                            save_negativita_to_customer(customer_name, details.get("data", {}))

                return result
            else:
                return {
                    "error": response_data.get("message", "Errore sconosciuto"),
                    "details": response_data
                }
        else:
            response_json = response.json() if response.text else {}
            return {
                "error": f"Errore API: {response.status_code}",
                "details": response_json
            }
    except Exception as e:
        return {"error": str(e)}


@frappe.whitelist()
def get_negativita_details(request_id):
    """
    Ottiene i dettagli della verifica negatività completata.

    Args:
        request_id: ID della richiesta completata

    Returns:
        dict con dettagli negatività
    """
    if not request_id:
        return {"error": "Request ID mancante"}

    url = common_data.get_service("Negativita Persona", f"IT-negativita/{request_id}/dettaglio")
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

            if response_data.get("success"):
                return {
                    "success": True,
                    "data": response_data.get("data", {})
                }
            else:
                return {
                    "error": response_data.get("message", "Errore sconosciuto"),
                    "details": response_data
                }
        else:
            response_json = response.json() if response.text else {}
            return {
                "error": f"Errore API: {response.status_code}",
                "details": response_json
            }
    except Exception as e:
        return {"error": str(e)}


@frappe.whitelist(allow_guest=True)
def handle_callback():
    """
    Gestisce il callback da OpenAPI quando la verifica è completata.
    Endpoint: /api/method/openapi.api.aziende.negativita_persona.handle_callback
    """
    try:
        data = frappe.request.get_json()

        if not data:
            frappe.log_error("Negatività Callback: nessun dato ricevuto", "OpenAPI Callback")
            return {"success": False, "error": "No data received"}

        request_id = data.get("id") or data.get("request_id")

        if not request_id:
            frappe.log_error(f"Negatività Callback: request_id mancante. Data: {data}", "OpenAPI Callback")
            return {"success": False, "error": "Missing request_id"}

        # Trova il Customer con questo request_id
        customer_name = frappe.db.get_value(
            "Customer",
            {"custom_negativita_request_id": request_id},
            "name"
        )

        if customer_name:
            # Ottieni i dettagli e salva
            details = get_negativita_details(request_id)

            if details.get("success"):
                save_negativita_to_customer(customer_name, details.get("data", {}))
                frappe.db.set_value("Customer", customer_name,
                                   "custom_negativita_status", "Completata")
            else:
                frappe.db.set_value("Customer", customer_name,
                                   "custom_negativita_status", "Errore")
                frappe.log_error(
                    f"Errore dettagli negatività per {customer_name}: {details}",
                    "OpenAPI Callback"
                )

            frappe.db.commit()
        else:
            frappe.log_error(
                f"Negatività Callback: Customer non trovato per request_id {request_id}",
                "OpenAPI Callback"
            )

        return {"success": True}

    except Exception as e:
        frappe.log_error(f"Negatività Callback Error: {str(e)}", "OpenAPI Callback")
        return {"success": False, "error": str(e)}


def save_negativita_to_customer(customer_name, data):
    """
    Salva i risultati della verifica negatività nel Customer.

    Args:
        customer_name: Nome del Customer
        data: Dati della verifica negatività
    """
    customer = frappe.get_doc("Customer", customer_name)

    # Conta negatività per tipo
    protesti = data.get("protesti", [])
    pregiudizievoli = data.get("pregiudizievoli", [])
    procedure = data.get("procedure_concorsuali", [])

    num_protesti = len(protesti) if isinstance(protesti, list) else 0
    num_pregiudizievoli = len(pregiudizievoli) if isinstance(pregiudizievoli, list) else 0
    num_procedure = len(procedure) if isinstance(procedure, list) else 0

    total_negativita = num_protesti + num_pregiudizievoli + num_procedure

    # Determina esito
    if total_negativita == 0:
        esito = "Nessuna negatività"
    else:
        esito = f"Trovate {total_negativita} negatività"

    # Aggiorna campi
    customer.custom_negativita_esito = esito
    customer.custom_negativita_protesti = num_protesti
    customer.custom_negativita_pregiudizievoli = num_pregiudizievoli
    customer.custom_negativita_procedure = num_procedure
    customer.custom_negativita_status = "Completata"
    customer.custom_negativita_check_date = frappe.utils.now()

    # Salva dettagli JSON per consultazione
    customer.custom_negativita_dettagli = json.dumps(data, indent=2, ensure_ascii=False)

    customer.save(ignore_permissions=True)
    frappe.db.commit()


@frappe.whitelist()
def get_customer_negativita(customer_name):
    """
    Avvia verifica negatività per un cliente esistente.

    Args:
        customer_name: Nome del documento Customer

    Returns:
        dict con risultato della richiesta
    """
    customer = frappe.get_doc("Customer", customer_name)

    if customer.customer_type != "Individual":
        return {"error": "La verifica negatività è disponibile solo per clienti Persona Fisica"}

    fiscal_code = customer.fiscal_code or customer.tax_id

    if not fiscal_code:
        return {"error": "Il cliente non ha codice fiscale"}

    # Verifica formato (deve essere CF persona fisica, non P.IVA)
    if len(fiscal_code) == 11 and fiscal_code.isdigit():
        return {"error": "Inserire il codice fiscale della persona, non la partita IVA"}

    return request_negativita_check(fiscal_code, customer_name)


@frappe.whitelist()
def check_customer_negativita_status(customer_name):
    """
    Controlla lo stato della verifica negatività per un cliente.

    Args:
        customer_name: Nome del documento Customer

    Returns:
        dict con stato e risultati
    """
    customer = frappe.get_doc("Customer", customer_name)

    request_id = customer.custom_negativita_request_id

    if not request_id:
        return {"error": "Nessuna verifica negatività in corso per questo cliente"}

    return check_request_status(request_id, customer_name)
