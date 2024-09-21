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

    if response.status_code == 200:
        uuid = response.json()["data"]["uuid"]

        transazione_sdi = frappe.new_doc("Transazione SDI")
        transazione_sdi.tipo_fattura = doctype
        transazione_sdi.fattura = doc.name
        transazione_sdi.stato_invio = "Inviata"
        transazione_sdi.uuid = uuid
        transazione_sdi.insert()

        doc.custom_transazione_sdi = transazione_sdi.name
        doc.save()
        return f"Fattura inviata: {response.json()['data']}"
    else:
        print(response.content)
        message = response.json().get("message", response.content)
        return f"Errore nella richiesta: {message}"

    return xml


@frappe.whitelist()
def download(docname, doctype, type):
    doc = frappe.get_doc(doctype, docname)
    company = frappe.get_doc("Company", doc.company)
    url = common_data.get_service("SDI", "invoices_download")

    if hasattr(doc, "custom_uuid"):
        url += f"/{doc.custom_uuid}"
    elif hasattr(doc, "uuid"):
        url += f"/{doc.uuid}"
    else:
        return "UUID non trovato"

    headers = {
        "Authorization": company.custom_open_api_token,
        "Accept": "application/" + type,
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        file_name = f"{doc.name}.{type}"
        # Imposta l'header della risposta per il download del file
        frappe.local.response.filename = file_name
        frappe.local.response.filecontent = response.content
        frappe.local.response.type = "download"
        frappe.response.display_content_as = "attachment"
    else:
        message = response.json().get("message", response.content)
        return f"Errore nella richiesta: {message}"
