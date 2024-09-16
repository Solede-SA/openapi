import italian_invoice.utilities.fatture as fatture
import openapi.tools.common_data as common_data
import frappe
import requests


def get_invoice_service_name(company):
    name = "invoices"
    if company.custom_apply_signature:
        name += "_signature"

    if company.custom_apply_legal_storage:
        name += "_legal_storage"

    return name


@frappe.whitelist()
def invia_fattura(docname, doctype):
    doc = frappe.get_doc(doctype, docname)
    company = frappe.get_doc("Company", doc.company)
    xml = fatture.get_xml(docname, doctype)
    service_name = get_invoice_service_name(company)
    url = common_data.get_service("SDI", service_name)

    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/xml",
    }
    response = requests.post(url, headers=headers, data=xml)

    print(response.content)

    if response.status_code == 200:
        uuid = response.json()["data"]["uuid"]
        doc.custom_uuid = uuid
        doc.custom_stato_invio = "Inviata"
        doc.save()
        return f"Fattura inviata: {response.json()['data']}"
    else:
        print(response.content)
        message = response.json().get("message", response.content)
        return f"Errore nella richiesta: {message}"

    return xml
