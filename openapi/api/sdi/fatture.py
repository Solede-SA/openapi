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
def verifica_stato_sdi(docname, doctype):
    """
    Emergenza SDI: interroga il provider per lo stato reale di una fattura già
    inviata e riallinea Transazione SDI se una notifica non ha mai aggiornato
    il documento (es. webhook non arrivato/non processato).
    """
    frappe.only_for("System Manager")

    info = frappe.db.get_value(doctype, docname, ["custom_transazione_sdi", "company"], as_dict=True)
    if not info.custom_transazione_sdi:
        frappe.throw("Questa fattura non ha una Transazione SDI associata.")

    provider = fatture.get_sdi_provider(info.company)
    return provider.reconcile_status(info.custom_transazione_sdi)


@frappe.whitelist()
def forza_reinvio_sdi(docname, doctype, motivo):
    """
    Emergenza SDI: forza il reinvio della fattura a SDI anche se già in stato
    "Inviata". Da usare solo quando è confermato (es. tramite verifica_stato_sdi)
    che SDI non ha mai ricevuto la trasmissione precedente - reinviare una
    fattura già consegnata a SDI genera una trasmissione duplicata.
    """
    frappe.only_for("System Manager")

    if not motivo or not motivo.strip():
        frappe.throw("Indicare un motivo per il reinvio di emergenza.")

    doc = frappe.get_doc(doctype, docname)
    transazione_precedente = doc.custom_transazione_sdi

    # Riusa lo stesso invio di invia_fattura(): non esiste un guard server-side
    # sullo stato, il "forzare" qui è la conferma esplicita di un System Manager.
    message = invia_fattura(docname, doctype)
    doc.reload()

    doc.add_comment(
        "Comment",
        f"Reinvio di emergenza a Sistema di Interscambio richiesto da {frappe.session.user}.<br>"
        f"Motivo: {motivo}<br>"
        f"Transazione SDI precedente: {transazione_precedente or 'nessuna'}<br>"
        f"Esito: {message}",
    )

    return message


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
