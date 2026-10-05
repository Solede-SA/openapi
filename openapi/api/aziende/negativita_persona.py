# Copyright (c) 2025, OpenAPI and contributors
# For license information, please see license.txt

import frappe
import json
import requests
import openapi.tools.common_data as common_data

# Secondi di attesa per chiamata: il job programmato non deve restare appeso
REQUEST_TIMEOUT = 30


def get_company_doc():
    return frappe.get_doc("Company", frappe.defaults.get_global_default("company"))


@frappe.whitelist()
def request_negativita_check(fiscal_code, customer_name=None):
    """
    Invia richiesta di verifica negatività per persona fisica o giuridica.
    Il risultato arriva in differita: lo raccoglie poll_pending_requests (o «Controlla Stato»).

    Args:
        fiscal_code: Codice fiscale della persona (16 caratteri) o dell'azienda (11 cifre)
        customer_name: Nome del Customer (opzionale, per salvare il request_id)

    Returns:
        dict con request_id e status
    """
    if not fiscal_code:
        return {"error": "Inserire codice fiscale"}

    # Pulisci l'input
    fiscal_code = fiscal_code.strip().upper().replace(" ", "")

    if not (len(fiscal_code) == 16 or (len(fiscal_code) == 11 and fiscal_code.isdigit())):
        return {"error": "Il codice fiscale deve essere di 16 caratteri (persona) o di 11 cifre (azienda)"}

    url = common_data.get_service("Negativita Persona", "IT-negativita")
    company = get_company_doc()

    if not company.custom_open_api_token:
        return {"error": "Token OpenAPI non configurato"}

    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }

    payload = {"cf_piva": fiscal_code}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)

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
                    "message": "Richiesta inviata. I risultati arrivano in automatico, oppure usa 'Controlla Stato'."
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
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

        if response.status_code == 200:
            response_data = response.json()

            if response_data.get("success"):
                data = response_data.get("data", {})
                status = data.get("status", "PENDING")

                result = {
                    "success": True,
                    "status": status,
                    "data": data
                }

                # Se completata, ottieni i dettagli; il Customer passa a «Completata» solo con i dettagli salvati
                if status == "COMPLETED":
                    details = get_negativita_details(request_id)
                    if details.get("error"):
                        return details
                    result["details"] = details["data"]

                    if customer_name:
                        save_negativita_to_customer(customer_name, details["data"])

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
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

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
    procedure = data.get("procedure", [])

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

    if customer.customer_type == "Company":
        fiscal_code = (customer.tax_id or "").upper().removeprefix("IT")
        if not fiscal_code:
            return {"error": "Il cliente non ha partita IVA"}
    else:
        # Persona fisica: serve il codice fiscale, non la partita IVA
        fiscal_code = customer.fiscal_code or customer.tax_id or ""
        if len(fiscal_code) != 16:
            return {"error": "Il cliente non ha un codice fiscale di persona valido (16 caratteri)"}

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


def poll_pending_requests():
    """Cron: raccoglie i risultati delle verifiche negatività in elaborazione.

    Schedulato ogni 10 minuti (vedi hooks.py). Il salvataggio del Customer avvisa le app
    che aspettano l'esito (es. daeok chiude i DAE Order in attesa).
    """
    for customer_name in frappe.get_all(
        "Customer", filters={"custom_negativita_status": "In Elaborazione"}, pluck="name"
    ):
        result = check_customer_negativita_status(customer_name)
        if result.get("error"):
            frappe.log_error(
                title="OpenAPI verifica negatività",
                message=f"poll_pending_requests: errore su {customer_name}: {result}",
            )
