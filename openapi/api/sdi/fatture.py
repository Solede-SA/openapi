# Wrapper per retrocompatibilità - delega al provider configurato
import italian_invoice.utilities.fatture as fatture
import frappe


@frappe.whitelist()
def invia_fattura(docname, doctype):
    """
    Wrapper per retrocompatibilità - usa il provider SDI configurato
    Mantiene la stessa interfaccia per compatibilità con codice esistente
    """
    doc = frappe.get_doc(doctype, docname)
    company = frappe.get_doc("Company", doc.company)

    # Ottieni provider configurato per la company
    provider = fatture.get_sdi_provider(doc.company)

    # Genera XML
    xml = fatture.get_xml(docname, doctype)

    # Invia tramite provider
    result = provider.send_invoice(xml, doc, company)

    # Ritorna messaggio compatibile con formato esistente
    if result.get("success"):
        return result.get("message")
    else:
        return result.get("message", "Errore invio fattura")


@frappe.whitelist()
def download(docname, doctype, type):
    """
    Wrapper per retrocompatibilità - usa il provider SDI configurato
    """
    doc = frappe.get_doc(doctype, docname)
    company = frappe.get_doc("Company", doc.company)

    # Ottieni UUID
    uuid = None
    if hasattr(doc, "custom_uuid"):
        uuid = doc.custom_uuid
    elif hasattr(doc, "uuid"):
        uuid = doc.uuid
    else:
        return "UUID non trovato"

    # Ottieni provider e scarica
    provider = fatture.get_sdi_provider(doc.company)

    try:
        content = provider.download_invoice(uuid, type, company)

        # Imposta risposta per download
        file_name = f"{doc.name}.{type}"
        frappe.local.response.filename = file_name
        frappe.local.response.filecontent = content
        frappe.local.response.type = "download"
        frappe.response.display_content_as = "attachment"
    except Exception as e:
        return f"Errore nella richiesta: {str(e)}"
