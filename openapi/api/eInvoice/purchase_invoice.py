import frappe
import json


@frappe.whitelist()
def process_supplier_invoice(json_data_string, fattura_fornitori_sdi):
    """
    Processa una fattura fornitore da una struttura JSON.

    Args:
        json_data_string: Una stringa che rappresenta la struttura JSON della fattura.
        fattura_fornitori_sdi: L'id del documento salvato in Fattura Fornitori SDI.

    Returns:
        Il codice (name) della fattura di acquisto creata.
    """

    # Verifica che il documento sia stato salvato in Fattura Fornitori SDI
    if not frappe.db.exists("Fattura Fornitori SDI", fattura_fornitori_sdi):
        frappe.throw("Documento non trovato in Fattura Fornitori SDI.")

    # get the document
    fattura_fornitori_sdi_doc = frappe.get_doc(
        "Fattura Fornitori SDI", fattura_fornitori_sdi
    )
    company = fattura_fornitori_sdi_doc.company

    try:
        # Converte la stringa JSON in un dizionario
        json_data = json.loads(json_data_string)

        # Estrai i dati dal JSON
        invoice_data = json_data["data"]["invoice"]
        payload = invoice_data["payload"]
        supplier_data = payload["fattura_elettronica_header"]["cedente_prestatore"]
        invoice_lines = payload["fattura_elettronica_body"][0]["dati_beni_servizi"][
            "dettaglio_linee"
        ]
        invoice_summary = payload["fattura_elettronica_body"][0]["dati_beni_servizi"][
            "dati_riepilogo"
        ]
        # Gestisci il caso in cui dati_pagamento è assente
        if payload["fattura_elettronica_body"][0]["dati_pagamento"]:
            payment_details = payload["fattura_elettronica_body"][0]["dati_pagamento"][
                0
            ]["dettaglio_pagamento"][0]
        else:
            payment_details = None  # Imposta un valore di default o gestisci l'assenza di dati di pagamento
            frappe.logger().warning(
                f"Dati di pagamento non trovati nella fattura {invoice_data['filename']}"
            )

        general_data = payload["fattura_elettronica_body"][0]["dati_generali"][
            "dati_generali_documento"
        ]

        # Estrai la partita IVA del fornitore
        supplier_vat_id = supplier_data["dati_anagrafici"]["id_fiscale_iva"][
            "id_codice"
        ]
        supplier_country_id = supplier_data["dati_anagrafici"]["id_fiscale_iva"][
            "id_paese"
        ]

        # Verifica il tipo di documento
        document_type_code = general_data["tipo_documento"]
        is_autofattura = check_document_type(document_type_code)
        if is_autofattura:
            frappe.throw(
                f"La fattura {invoice_data['filename']} è una autofattura e non verrà importata."
            )

        # Controlla se il fornitore esiste
        supplier = frappe.db.exists("Supplier", {"tax_id": supplier_vat_id})

        if not supplier:
            # Crea il fornitore
            supplier = create_supplier(supplier_data, company)
            frappe.logger().info(f"Fornitore '{supplier}' creato con successo.")
        else:
            frappe.logger().info(f"Fornitore '{supplier}' già esistente.")

        # Crea la fattura di acquisto
        purchase_invoice = create_purchase_invoice(
            company,
            invoice_data,
            supplier,
            invoice_lines,
            invoice_summary,
            payment_details,
            general_data,
        )
        frappe.logger().info(
            f"Fattura di acquisto '{invoice_data['filename']}' creata con successo."
        )

        # Aggiorna il documento Fattura Fornitori SDI
        fattura_fornitori_sdi_doc.fattura = purchase_invoice
        fattura_fornitori_sdi_doc.stato = "Importata"
        fattura_fornitori_sdi_doc.save()

        return purchase_invoice.name

    except Exception as e:
        frappe.logger().error(f"Errore durante l'elaborazione della fattura: {e}")
        frappe.throw(f"Errore durante l'elaborazione della fattura: {e}")


def create_supplier(supplier_data, company):
    """
    Crea un nuovo fornitore.

    Args:
        supplier_data: Un dizionario con i dati del fornitore.

    Returns:
        Il nome del documento del fornitore creato.
    """

    companyDoc = frappe.get_doc("Company", company)

    supplier = frappe.get_doc(
        {
            "doctype": "Supplier",
            "supplier_name": supplier_data["dati_anagrafici"]["anagrafica"][
                "denominazione"
            ],
            "tax_id": supplier_data["dati_anagrafici"]["id_fiscale_iva"]["id_codice"],
            "supplier_group": _get_supplier_group(),
            "supplier_type": "Company",
            "tax_country": supplier_data["dati_anagrafici"]["id_fiscale_iva"][
                "id_paese"
            ],
            "address_line1": supplier_data["sede"]["indirizzo"],
            "address_line2": supplier_data["sede"]["numero_civico"],
            "city": supplier_data["sede"]["comune"],
            "state": supplier_data["sede"]["provincia"],
            "pincode": supplier_data["sede"]["cap"],
            "country": get_country_name(
                supplier_data["sede"]["nazione"]
            ),  # Utilizzo della funzione get_country_name
            "is_frozen": 0,
            "status": "Passive",
        }
    )

    # Gestione campo opzionale 'contatti'
    if supplier_data["contatti"] is not None:
        if (
            "telefono" in supplier_data["contatti"]
            and supplier_data["contatti"]["telefono"]
        ):
            supplier.phone = supplier_data["contatti"]["telefono"]
        if "fax" in supplier_data["contatti"] and supplier_data["contatti"]["fax"]:
            supplier.fax = supplier_data["contatti"]["fax"]
        if "email" in supplier_data["contatti"] and supplier_data["contatti"]["email"]:
            supplier.email_id = supplier_data["contatti"]["email"]

    # se abbiamo il codice fiscale e non è un codice temporaneo (11 numeri)
    if (
        supplier_data["dati_anagrafici"]["codice_fiscale"]
        and len(supplier_data["dati_anagrafici"]["codice_fiscale"]) != 11
    ):
        supplier.supplier_type = "Individual"

    supplier.insert()
    supplier.save()
    return supplier.name


def create_purchase_invoice(
    company,
    invoice_data,
    supplier,
    invoice_lines,
    invoice_summary,
    payment_details,
    general_data,
):
    """
    Crea una nuova fattura di acquisto.

    Args:
        company: Nome della società.
        invoice_data: Dati generali della fattura.
        supplier: Nome del documento del fornitore.
        invoice_lines: Lista di righe della fattura.
        invoice_summary: Lista di riepiloghi iva.
        payment_details: Dettagli di pagamento
        general_data: Dati generali del documento
    """

    # Gestisci l'assenza di dati di pagamento
    if payment_details:
        payments = _prepare_payment_schedule(payment_details)
    else:
        payments = []

    purchase_invoice = frappe.get_doc(
        {
            "doctype": "Purchase Invoice",
            "supplier": supplier,
            "posting_date": general_data["data"],
            # "due_date": payment_details["data_scadenza_pagamento"],
            "company": company,
            "currency": general_data["divisa"],
            "is_paid": 0,  # imposta la fattura come non pagata
            "status": "Draft",  # imposta la fattura come bozza
            # "payment_terms_template": _get_payment_terms(
            #     payment_details["condizioni_pagamento"]
            # ),
            # "taxes_and_charges": _get_default_tax_template(),  # Funzione di supporto per ottenere il template di tasse e spese
            "scan_field": invoice_data["file_id"],
            "from_xml": 1,  # flag per tenere traccia delle fatture importate da xml
            "bill_no": general_data["numero"],  # Numero della fattura elettronica
            "bill_date": general_data["data"],  # Data della fattura elettronica
            "items": _prepare_invoice_items(invoice_lines, company),
            "taxes": _prepare_invoice_taxes(invoice_summary, company),
            "payments": payments,
        }
    )

    purchase_invoice.insert()
    purchase_invoice.save()

    return purchase_invoice
    # purchase_invoice.submit() # Scommentare per validare automaticamente la fattura


def _prepare_invoice_items(invoice_lines, company):
    """
    Prepara le righe della fattura di acquisto.

    Args:
        invoice_lines: Lista di righe della fattura.
        company: Nome della società.

    Returns:
        Una lista di dizionari che rappresentano le righe della fattura di acquisto.
    """
    items = []
    for line in invoice_lines:
        items.append(
            {
                "item_code": _get_item_code(line),
                "description": line["descrizione"],
                "qty": line["quantita"] if line["quantita"] else 1,
                "rate": line["prezzo_unitario"],
                "uom": _get_uom(),
                "price_list_rate": line["prezzo_unitario"],
                "discount_amount": 0,
                "tax_rate": line["aliquota_iva"],
            }
        )
    return items


def _prepare_invoice_taxes(invoice_summary, company):
    """
    Prepara le tasse per la fattura di acquisto.

    Args:
        invoice_summary: Lista di riepiloghi iva.
        company: Nome della società.

    Returns:
        Una lista di dizionari che rappresentano le tasse della fattura.
    """
    taxes = []
    for summary in invoice_summary:
        tax_account = _get_tax_account(summary["aliquota_iva"], company)
        taxes.append(
            {
                "charge_type": "Actual",
                "account_head": tax_account,
                "tax_amount": summary["imposta"],
                "description": f"IVA {summary['aliquota_iva']}%",
                "total": summary["imponibile_importo"],
            }
        )
    return taxes


def _prepare_payment_schedule(payment_details):
    """
    Prepara lo schema dei pagamenti per la fattura.

    Args:
        payment_details: Dettagli di pagamento.

    Returns:
        Una lista di dizionari che rappresentano lo schema dei pagamenti.
    """
    payment_schedule = []
    payment_schedule.append(
        {
            "due_date": payment_details["data_scadenza_pagamento"],
            "payment_amount": payment_details["importo_pagamento"],
        }
    )
    return payment_schedule


# --- Funzioni di supporto ---


def _get_supplier_group():
    """
    Restituisce il gruppo di fornitori di default.
    Da implementare in base alla propria configurazione.
    """
    return "Servizi"


def _get_default_tax_template():
    """
    Restituisce il tax template di default
    Da implementare in base alla propria configurazione.
    """
    return ""


def _get_payment_terms(payment_code):
    """
    Restituisce il template dei termini di pagamento in base al codice
    Da implementare in base alla propria configurazione.
    ad esempio:
    if payment_code == 'TP02':
        return 'Pagamento Completo'
    """
    return ""


def _get_item(line):
    """
    Restituisce l'item_code in base alla descrizione della riga.
    Da implementare in base alla propria configurazione.
    Si potrebbe usare la descrizione per cercare un item esistente o crearne uno nuovo.
    """
    item_code = frappe.db.get_value("Item", {"item_name": line["descrizione"]}, "name")
    if item_code:
        return item_code
    else:
        # Crea un nuovo item (configurazione minima)
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": line[
                    "descrizione"
                ],  # Da migliorare: potresti usare un prefisso o un codice generato automaticamente
                "item_name": line["descrizione"],
                # "item_group": _get_item_group(),  # Funzione di supporto per ottenere il gruppo articolo di default
                "description": line["descrizione"],
                "is_stock_item": 0,
                "show_in_website": 0,
                "taxes": [],  # aggiungere eventuale configurazione iva
            }
        )
        item.insert()
        return item.item_code


def _get_item_group():
    """
    Restituisce il gruppo articolo di default.
    Da implementare in base alla propria configurazione.
    """
    return "All Item Groups"


def _get_uom():
    """
    Restituisce l'uom di default.
    Da implementare in base alla propria configurazione.
    """
    return "Nr"


def _get_warehouse():
    """
    Restituisce il magazzino di default.
    Da implementare in base alla propria configurazione.
    """
    return frappe.get_value("Warehouse", {"company": _get_company()}, "name")


def _get_tax_account(tax_rate, company):
    """
    Restituisce l'account iva in base all'aliquota
    """
    return "06081084 - ALTRE IMPOSTE E TASSE - CBM"
    # tax_account = frappe.db.get_all(
    #     "Purchase Taxes and Charges Template",
    #     {"company": company, "tax_rate": tax_rate},
    #     ["name"],
    # )
    # if tax_account:
    #     doc = frappe.get_doc("Purchase Taxes and Charges Template", tax_account[0].name)
    #     return doc.taxes[0].account_head


def get_country_name(country_code):
    """
    Restituisce il nome completo del paese a partire dal codice a due lettere.

    Args:
        country_code: Il codice del paese a due lettere (es. "IT").

    Returns:
        Il nome completo del paese (es. "Italy") o None se il codice non è valido.
    """
    if not country_code:
        return None

    # Normalizza il codice paese in maiuscolo
    country_code = country_code.upper()

    # Mappa i codici speciali
    if country_code == "UK":
        country_code = "GB"

    # Dizionario statico di mappatura (da completare se necessario)
    country_mapping = {
        "IT": "Italy",
        "DE": "Germany",
        "FR": "France",
        "ES": "Spain",
        "GB": "United Kingdom",
        # ... aggiungi altre nazioni qui ...
    }

    # Usa frappe.local.countries per la conversione
    return country_mapping.get(country_code)


def _get_item_code(line):
    """
    Restituisce l'item_code. Se non esiste, restituisce l'item generico.
    """
    item_code = frappe.db.get_value("Item", {"item_name": line["descrizione"]}, "name")
    if item_code:
        return item_code
    else:
        return "Servizi Generici"


def check_document_type(document_type_code):
    """
    Verifica il tipo di documento e avvisa se è un'autofattura.

    Args:
        document_type_code: Il codice del tipo di documento (es. "TD01").

    Returns:
        True se è un'autofattura, False altrimenti.
    """
    try:
        doc_type = frappe.get_doc(
            "Tipologia di documento e-Invoice", document_type_code
        )
        if doc_type.tipologia == "AutoFattura":
            frappe.msgprint(
                f"Attenzione: Il documento con codice {document_type_code} è una autofattura e non verrà importato.",
                title="Autofattura rilevata",
                indicator="red",
            )
            return True
    except frappe.DoesNotExistError:
        frappe.logger().warning(
            f"Tipo documento {document_type_code} non trovato in 'Tipologia di documento e-Invoice'"
        )
    return False
