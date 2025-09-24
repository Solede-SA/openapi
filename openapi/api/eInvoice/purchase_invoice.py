# Wrapper per retrocompatibilità - delega a italian_invoice
import frappe
import json
from italian_invoice.utilities import fatture_passive


@frappe.whitelist()
def get_or_create_supplier(supplier_vat_id, fattura_fornitori_sdi):
    """
    Wrapper per retrocompatibilità - usa italian_invoice

    Args:
        supplier_vat_id: Partita IVA del fornitore
        fattura_fornitori_sdi: Nome del documento Fattura Fornitori SDI per recuperare i dati

    Returns:
        dict: Dati del fornitore (esistente o appena creato)
    """
    try:
        # Se viene passato il documento SDI, recupera i dati
        if fattura_fornitori_sdi and frappe.db.exists("Fattura Fornitori SDI", fattura_fornitori_sdi):
            sdi_doc = frappe.get_doc("Fattura Fornitori SDI", fattura_fornitori_sdi)
            invoice_data = json.loads(sdi_doc.dati_fattura)
        else:
            invoice_data = {}

        # Delega a italian_invoice
        return fatture_passive.get_or_create_supplier(supplier_vat_id, invoice_data)

    except Exception as e:
        frappe.log_error(f"Errore wrapper get_or_create_supplier: {str(e)}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def process_supplier_invoice(
    json_data_string, fattura_fornitori_sdi, item_mappings=None
):
    """
    Wrapper per retrocompatibilità - delega a italian_invoice
    Mantiene la stessa interfaccia per compatibilità con codice esistente
    """
    try:
        # Delega completamente a italian_invoice
        return fatture_passive.process_supplier_invoice(
            json_data_string,
            fattura_fornitori_sdi,
            item_mappings
        )

    except Exception as e:
        frappe.log_error(f"Errore wrapper process_supplier_invoice: {str(e)}")
        frappe.throw(f"Errore importazione: {str(e)}")


# Wrapper per funzioni helper - manteniamo per retrocompatibilità
# Nel caso qualche codice custom le chiami direttamente

def create_supplier(supplier_data, company):
    """Wrapper per retrocompatibilità - usa italian_invoice"""
    return fatture_passive.create_supplier(supplier_data, company)


def _prepare_invoice_items(invoice_lines, company):
    """Wrapper per retrocompatibilità - usa italian_invoice"""
    return fatture_passive.prepare_invoice_items(invoice_lines, None, company)


def _prepare_invoice_items_with_mapping(invoice_lines, mappings):
    """Wrapper per retrocompatibilità - usa italian_invoice"""
    # Assumiamo che la company sia nel contesto o usa default
    company = frappe.defaults.get_user_default("Company")
    return fatture_passive.prepare_invoice_items(invoice_lines, mappings, company)


def _prepare_invoice_taxes(invoice_summary, company):
    """Wrapper per retrocompatibilità - usa italian_invoice"""
    return fatture_passive.prepare_invoice_taxes(invoice_summary, company)


def _get_supplier_group():
    """Wrapper per retrocompatibilità - usa italian_invoice"""
    return fatture_passive.get_default_supplier_group()


def _get_uom():
    """Wrapper per retrocompatibilità - usa italian_invoice"""
    return fatture_passive.get_default_uom()


def _get_tax_account(tax_rate, company):
    """Wrapper per retrocompatibilità - usa italian_invoice"""
    return fatture_passive.get_tax_account(tax_rate, company)


def get_country_name(country_code):
    """Wrapper per retrocompatibilità - usa italian_invoice"""
    return fatture_passive.get_country_name(country_code)


def _get_item_code(line):
    """Wrapper per retrocompatibilità - usa italian_invoice"""
    return fatture_passive.get_or_create_item_code(line)


@frappe.whitelist()
def check_document_type(document_type_code):
    """Wrapper per retrocompatibilità - usa italian_invoice"""
    return fatture_passive.check_document_type(document_type_code)