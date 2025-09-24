import frappe
import json
from dateutil.parser import parse
from datetime import datetime
import pytz
import pprint
import logging

# Configurazione logger
logger = logging.getLogger("openapi.sdi")
logger.setLevel(logging.INFO)

# Configurazione dell'handler per scrivere su file
import os
log_file = os.path.join(frappe.utils.get_bench_path(), "logs", "openapi_sdi.log")
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)

# Formato del log
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Aggiungiamo l'handler al logger
logger.addHandler(file_handler)


def search_value_in_json(data, target_key):
    """
    Cerca ricorsivamente un valore in una struttura JSON dato un determinato nome di chiave o un percorso parziale.

    :param data: La struttura JSON in cui cercare.
    :param target_key: Il nome della chiave del valore da cercare o un percorso parziale.
    :return: Una lista di valori trovati per la chiave specificata o il percorso parziale.
    """
    keys = target_key.split(".")

    def search(data, keys):
        if not keys:
            yield data
            return

        current_key = keys[0]
        remaining_keys = keys[1:]

        if isinstance(data, dict):
            for key, value in data.items():
                if key == current_key:
                    yield from search(value, remaining_keys)
                if isinstance(value, (dict, list)):
                    yield from search(value, keys)
        elif isinstance(data, list):
            for item in data:
                yield from search(item, keys)

    results = list(search(data, keys))
    if len(results) == 1:
        return results[0]
    return results


def get_data_ok(request):
    data = json.loads(frappe.request.data)
    # pprint.pp(data)
    event = data["event"]
    lista_errori = ""
    stato = ""

    if event == "customer-notification":
        uuid = data["data"]["notification"]["invoice_uuid"]
        data_notifica = data["data"]["notification"]["created_at"]
        stato = data["data"]["notification"]["type"]

        if stato == "NE":
            stato = data["data"]["notification"]["message"]["esito_committente"][
                "esito"
            ]

        # Check if "lista_errori" exists
        lista_errori = data["data"]["notification"]["message"].get("lista_errori", "")

    elif event == "customer-invoice":
        uuid = data["data"]["invoice"]["uuid"]
        data_notifica = data["data"]["invoice"]["created_at"]
        stato = "Inviata"

    elif event == "legal-storage-receipt":
        uuid = data["data"]["object_id"]
        # Use updated_at if receipt_received_at is not present
        data_notifica = data["data"].get("receipt_received_at", data["data"]["updated_at"])
        stato = data["data"].get("status", "")

    lista_transazioni = frappe.get_list(
        "Transazione SDI",
        filters={"uuid": uuid},
        fields=["name"],
    )
    if len(lista_transazioni) > 0:
        transazione = frappe.get_doc("Transazione SDI", lista_transazioni[0]["name"])

        data_ok = {
            "doc_transazione": transazione,
            "event": event,
            "uuid": uuid,
            "original_data": data,
            "data_notifica": data_notifica,
            "stato": stato,
            "lista_errori": lista_errori,
        }

        return data_ok
    else:
        frappe.throw(f"Transazione non trovata: {uuid}")


def save_notifica(data_ok):
    transazione = data_ok["doc_transazione"]
    fattura = frappe.get_doc(transazione.tipo_fattura, transazione.fattura)
    data_notifica_str = data_ok["data_notifica"]
    data_notifica = parse(data_notifica_str)
    # Convertire `data_notifica` in UTC
    rome_tz = pytz.timezone("Europe/Rome")
    # Convertire `data_notifica` al fuso orario di Roma
    data_notifica_rome = data_notifica.astimezone(rome_tz)

    # Formattare la data in un formato compatibile con il database SQL
    formatted_data_notifica = data_notifica_rome.strftime("%Y-%m-%d %H:%M:%S")

    # Convertire `original_data` in un oggetto Python e poi in una stringa JSON indentata
    formatted_original_data = json.dumps(data_ok["original_data"], indent=2)

    transazione.append(
        "notifiche_sdi",
        {
            "notifica": data_ok["event"],
            "data": formatted_original_data,
            "data_notifica": formatted_data_notifica,
            "uuid": data_ok["uuid"],
        },
    )
    transazione.ultima_notifica = formatted_original_data
    transazione.stato_invio = data_ok["stato"]
    transazione.save()

    fattura.custom_transazione_sdi = transazione.name
    fattura.save()


@frappe.whitelist(allow_guest=True)
def supplier_invoice():
    """
    Wrapper per retrocompatibilità - delega al provider SDI
    Mantiene allow_guest=True per compatibilità
    """
    try:
        import italian_invoice.utilities.fatture as fatture
        data = json.loads(frappe.request.data)

        # Delega al router centrale
        result = fatture.handle_sdi_webhook("supplier_invoice", data)

        # Ritorna formato compatibile
        if result.get("success"):
            return "OK from supplier_invoice"
        else:
            frappe.throw(result.get("message", "Errore elaborazione"))

    except Exception as e:
        logger.exception(f"Errore supplier_invoice: {str(e)}")
        frappe.log_error(str(e), "Supplier Invoice Error")
        raise


@frappe.whitelist(allow_guest=False)
def cutomer_invoice():
    data_ok = get_data_ok(frappe.request.data)
    save_notifica(data_ok)

    return "OK from customer_invoice"


@frappe.whitelist(allow_guest=False)
def invoice_status_quarantena():
    print(frappe.request.data)
    return "OK from invoice_status_quarantena"


@frappe.whitelist(allow_guest=False)
def invoice_status_invoice_error():
    print(frappe.request.data)
    return "OK from invoice_status_invoice_error"


@frappe.whitelist(allow_guest=False)
def customer_notification():
    """
    Wrapper per retrocompatibilità - delega al provider SDI
    """
    try:
        import italian_invoice.utilities.fatture as fatture
        data = json.loads(frappe.request.data)

        # Delega al router centrale
        result = fatture.handle_sdi_webhook("customer_notification", data)

        # Ritorna formato compatibile
        if result.get("success"):
            return "OK from customer_notification"
        else:
            frappe.throw(result.get("message", "Errore elaborazione"))

    except Exception as e:
        logger.exception(f"Errore customer_notification: {str(e)}")
        raise


@frappe.whitelist(allow_guest=False)
def legal_storage_missing_vat():
    print(frappe.request.data)
    return "OK from legal_storage_missing_vat"


@frappe.whitelist(allow_guest=False)
def legal_storage_receipt():
    """
    Wrapper per retrocompatibilità - delega al provider SDI
    """
    try:
        import italian_invoice.utilities.fatture as fatture
        data = json.loads(frappe.request.data)

        # Delega al router centrale
        result = fatture.handle_sdi_webhook("legal_storage_receipt", data)

        # Ritorna formato compatibile
        if result.get("success"):
            return "OK from legal_storage_receipt"
        else:
            frappe.throw(result.get("message", "Errore elaborazione"))

    except Exception as e:
        logger.exception(f"Errore legal_storage_receipt: {str(e)}")
        raise
