import frappe
import requests


def get_service(name, endpoint="business_registry_configurations"):
    url = frappe.get_value("OpenApi Services", name, "url")
    urlOk = url + "/" + endpoint

    return urlOk


def prepare_data(data):
    data = frappe.parse_json(data)
    data["apply_legal_storage"] = bool(data.get("apply_legal_storage", False))
    data["apply_signature"] = bool(data.get("apply_signature", False))

    return data


@frappe.whitelist()
def create_business_register(data):
    data = prepare_data(data)
    company = frappe.get_doc("Company", data["name"])
    url = get_service("SDI")
    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=data)

    # Verifica se la richiesta è andata a buon fine
    if response.status_code == 200:
        return response.json()["data"]
    else:
        message = response.json().get("message", response.content)
        frappe.throw(f"Errore nella richiesta: {message}")


def prepare_configuration(company):
    fiscal_id = company.tax_id
    callbacks = []

    for webhook in company.custom_elenco_webhook:
        callback = {
            "event": webhook.event,
            "url": company.custom_webhook_url + webhook.url,
            "auth_header": company.custom_auth_header,
        }
        callbacks.append(callback)

    configuration = {"fiscal_id": fiscal_id, "callbacks": callbacks}

    return frappe.parse_json(configuration)


@frappe.whitelist()
def send_configuration(data):
    data = prepare_data(data)
    company = frappe.get_doc("Company", data["name"])
    configuration = prepare_configuration(company)
    url = get_service("SDI", "api_configurations")

    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=configuration)

    # Verifica se la richiesta è andata a buon fine
    if response.status_code == 200:
        return response.json()["data"]
    else:
        message = response.json().get("message", response.content)
        frappe.throw(f"Errore nella richiesta: {message}")


@frappe.whitelist()
def check_business_register(data):
    data = prepare_data(data)
    company = frappe.get_doc("Company", data["name"])
    url = get_service("SDI")
    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }
    response = requests.get(url, headers=headers, params=data)

    print(response.content)

    # Verifica se la richiesta è andata a buon fine
    if response.status_code == 200:
        return f"Prova: {response.json()['data']}"
    else:
        print(response.content)
        message = response.json().get("message", response.content)
        return f"Errore nella richiesta: {message}"
