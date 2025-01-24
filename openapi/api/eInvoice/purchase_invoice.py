import frappe
import json


@frappe.whitelist()
def get_or_create_supplier(supplier_vat_id, fattura_fornitori_sdi):
    """
    Controlla se esiste un fornitore con la partita IVA data, altrimenti lo crea

    Args:
        supplier_vat_id: Partita IVA del fornitore
        fattura_fornitori_sdi: Nome del documento Fattura Fornitori SDI per recuperare i dati

    Returns:
        dict: Dati del fornitore (esistente o appena creato)
    """
    try:
        # Cerca fornitore esistente
        supplier = frappe.db.exists("Supplier", {"tax_id": supplier_vat_id})

        if supplier:
            # Ritorna i dati del fornitore esistente
            supplier_doc = frappe.get_doc("Supplier", supplier)
            return {
                "success": True,
                "supplier_name": supplier_doc.name,
                "supplier_data": supplier_doc.as_dict(),
                "is_new": False,
            }

        # Se non esiste, recupera i dati dalla fattura SDI
        sdi_doc = frappe.get_doc("Fattura Fornitori SDI", fattura_fornitori_sdi)
        json_data = json.loads(sdi_doc.dati_fattura)
        supplier_data = json_data["data"]["invoice"]["payload"][
            "fattura_elettronica_header"
        ]["cedente_prestatore"]

        # Crea nuovo fornitore
        new_supplier = create_supplier(supplier_data, sdi_doc.company)

        supplier_doc = frappe.get_doc("Supplier", new_supplier)
        return {
            "success": True,
            "supplier_name": supplier_doc.name,
            "supplier_data": supplier_doc.as_dict(),
            "is_new": True,
        }

    except Exception as e:
        frappe.log_error(f"Errore in get_or_create_supplier: {str(e)}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def process_supplier_invoice(
    json_data_string, fattura_fornitori_sdi, item_mappings=None
):
    try:
        frappe.db.begin()

        if not frappe.db.exists("Fattura Fornitori SDI", fattura_fornitori_sdi):
            frappe.throw("Documento non trovato")

        if item_mappings and isinstance(item_mappings, str):
            item_mappings = json.loads(item_mappings)

        fattura_fornitori_sdi_doc = frappe.get_doc(
            "Fattura Fornitori SDI", fattura_fornitori_sdi
        )
        json_data = json.loads(json_data_string)
        payload = json_data["data"]["invoice"]["payload"]

        supplier_vat = payload["fattura_elettronica_header"]["cedente_prestatore"][
            "dati_anagrafici"
        ]["id_fiscale_iva"]["id_codice"]
        supplier_result = get_or_create_supplier(supplier_vat, fattura_fornitori_sdi)

        if not supplier_result["success"]:
            frappe.db.rollback()
            frappe.throw(f"Errore fornitore: {supplier_result['error']}")

        supplier = supplier_result["supplier_name"]

        purchase_invoice = frappe.get_doc(
            {
                "doctype": "Purchase Invoice",
                "supplier": supplier,
                "posting_date": payload["fattura_elettronica_body"][0]["dati_generali"][
                    "dati_generali_documento"
                ]["data"],
                "company": fattura_fornitori_sdi_doc.company,
                "currency": payload["fattura_elettronica_body"][0]["dati_generali"][
                    "dati_generali_documento"
                ]["divisa"],
                "is_paid": 0,
                "status": "Draft",
                "scan_field": json_data["data"]["invoice"]["file_id"],
                "from_xml": 1,
                "bill_no": payload["fattura_elettronica_body"][0]["dati_generali"][
                    "dati_generali_documento"
                ]["numero"],
                "bill_date": payload["fattura_elettronica_body"][0]["dati_generali"][
                    "dati_generali_documento"
                ]["data"],
                "items": (
                    _prepare_invoice_items_with_mapping(
                        payload["fattura_elettronica_body"][0]["dati_beni_servizi"][
                            "dettaglio_linee"
                        ],
                        item_mappings,
                    )
                    if item_mappings
                    else _prepare_invoice_items(
                        payload["fattura_elettronica_body"][0]["dati_beni_servizi"][
                            "dettaglio_linee"
                        ],
                        fattura_fornitori_sdi_doc.company,
                    )
                ),
                "taxes": _prepare_invoice_taxes(
                    payload["fattura_elettronica_body"][0]["dati_beni_servizi"][
                        "dati_riepilogo"
                    ],
                    fattura_fornitori_sdi_doc.company,
                ),
            }
        )

        purchase_invoice.insert()
        purchase_invoice.save()

        fattura_fornitori_sdi_doc.fattura = purchase_invoice
        fattura_fornitori_sdi_doc.stato = "Importata"
        fattura_fornitori_sdi_doc.save()

        frappe.db.commit()
        return purchase_invoice.name

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Errore: {str(e)}\nJSON: {json_data_string}")
        frappe.throw(f"Errore importazione: {str(e)}")


def _prepare_invoice_items_with_mapping(invoice_lines, mappings):
    items = []
    for line in invoice_lines:
        mapping = mappings.get(str(line["numero_linea"]))
        if mapping:
            # Get UOM from item defaults
            uom = frappe.db.get_value("Item", mapping["item_code"], "stock_uom") or "Nr"
            items.append(
                {
                    "item_code": mapping["item_code"],
                    "description": mapping["description"],
                    "qty": line["quantita"] if line["quantita"] else 1,
                    "rate": line["prezzo_unitario"],
                    "expense_account": mapping["account"],
                    "uom": uom,
                    "price_list_rate": line["prezzo_unitario"],
                    "tax_rate": line["aliquota_iva"],
                    "tax_nature": line.get("natura"),
                }
            )
    return items


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
                "rate": summary["aliquota_iva"],
                "description": f"IVA {summary['aliquota_iva']}%",
                "total": summary["imponibile_importo"],
            }
        )
    print("taxes", taxes)
    return taxes


def _get_supplier_group():
    """
    Restituisce il gruppo di fornitori di default.
    Da implementare in base alla propria configurazione.
    """
    return "Servizi"


def _get_uom():
    """
    Restituisce l'uom di default.
    Da implementare in base alla propria configurazione.
    """
    return "Nr"


def _get_tax_account(tax_rate, company):
    """
    Restituisce l'account iva in base all'aliquota
    """
    # rendo tax_rate un numero con due decimali
    tax_rate = round(float(tax_rate), 2)

    default_tax_account = "01073004 - IVA ACQUISTI - CBM"

    if tax_rate > 0:
        tax_account = frappe.db.get_all(
            "Account",
            {"company": company, "tax_rate": tax_rate, "root_type": "Asset"},
            ["name"],
        )
        if tax_account:
            default_tax_account = tax_account[0]["name"]

    return default_tax_account


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
