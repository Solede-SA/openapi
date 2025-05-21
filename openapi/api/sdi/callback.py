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
    try:
        # Utilizziamo il logger standard invece di log_error
        logger.info("Inizio elaborazione fattura fornitore")
        
        # Log limitato dei dati ricevuti
        data_preview = str(frappe.request.data)[:100] + "..." if len(str(frappe.request.data)) > 100 else str(frappe.request.data)
        logger.info(f"Preview dati ricevuti: {data_preview}")
        
        data = json.loads(frappe.request.data)
        logger.info("Parsing JSON completato")
        
        partita_iva_company = search_value_in_json(
            data,
            "cessionario_committente.dati_anagrafici.id_fiscale_iva.id_codice",
        )
        if partita_iva_company:
            logger.info(f"Partita IVA azienda estratta: {partita_iva_company}")
        else:
            logger.warning("Partita IVA azienda non trovata")

        partita_iva_fornitore = search_value_in_json(
            data,
            "cedente_prestatore.dati_anagrafici.id_fiscale_iva.id_codice",
        )
        if partita_iva_fornitore:
            logger.info(f"Partita IVA fornitore estratta: {partita_iva_fornitore}")
        else:
            logger.warning("Partita IVA fornitore non trovata")

        denominazione_fornitore = search_value_in_json(
            data,
            "cedente_prestatore.dati_anagrafici.anagrafica.denominazione",
        )
        if denominazione_fornitore:
            logger.info(f"Denominazione fornitore estratta: {denominazione_fornitore}")
        else:
            logger.warning("Denominazione fornitore non trovata")

        print(f"partita_iva_fornitore: {partita_iva_fornitore}")
        print(f"denominazione_fornitore: {denominazione_fornitore}")

        logger.info("Ricerca company iniziata")
        company_list = frappe.get_list("Company", filters={"tax_id": partita_iva_company})
        logger.info(f"Trovate {len(company_list)} company")
        
        if len(company_list) == 0:
            error_msg = f"Company non trovata: {partita_iva_company}"
            logger.error(error_msg)
            # Qui possiamo usare log_error per rendere visibile nell'interfaccia utente
            frappe.log_error(error_msg, "Supplier Invoice Error")
            frappe.throw(error_msg)
        else:
            company = frappe.get_doc("Company", company_list[0]["name"])
            logger.info(f"Company trovata: {company.name}")

        uuid = search_value_in_json(data, "invoice.uuid")
        if uuid:
            logger.info(f"UUID estratto: {uuid}")
        else:
            logger.warning("UUID non trovato")

        logger.info("Creazione documento fattura fornitore")
        fattura_fornitore = frappe.new_doc("Fattura Fornitori SDI")
        fattura_fornitore.dati_fattura = json.dumps(data, indent=2)
        fattura_fornitore.uuid = uuid
        fattura_fornitore.company = company
        fattura_fornitore.partita_iva_fornitore = partita_iva_fornitore
        fattura_fornitore.denominazione_fornitore = denominazione_fornitore
        fattura_fornitore.via_webhook = 1
        
        # Imposta il flag per ignorare la validazione anche in produzione
        fattura_fornitore.flags.ignore_validate = True

        logger.info("Inserimento fattura fornitore")
        fattura_fornitore.insert()
        logger.info(f"Fattura fornitore inserita con successo: {fattura_fornitore.name}")
        
        return "OK from supplier_invoice"
    except Exception as e:
        error_details = f"Errore durante l'elaborazione della fattura fornitore: {str(e)}\n{frappe.get_traceback()}"
        logger.exception(error_details)
        # Registriamo l'errore anche nel log di Frappe per maggiore visibilità
        frappe.log_error(error_details, "Supplier Invoice Error")
        # Rilancia l'eccezione per restituire l'errore HTTP
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
    data_ok = get_data_ok(frappe.request.data)
    save_notifica(data_ok)

    return "OK from customer_notification"


@frappe.whitelist(allow_guest=False)
def legal_storage_missing_vat():
    print(frappe.request.data)
    return "OK from legal_storage_missing_vat"


@frappe.whitelist(allow_guest=False)
def legal_storage_receipt():
    # Skip saving notification for legal-storage-receipt events
    # data_ok = get_data_ok(frappe.request.data)
    # save_notifica(data_ok)
    return "OK from legal_storage_receipt"
