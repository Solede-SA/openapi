// Custom Supplier JS - Integrazione OpenAPI
// Copyright (c) 2025, OpenAPI and contributors
// For license information, please see license.txt

frappe.ui.form.on('Supplier', {
    onload: function(frm) {
        if (frm.is_new()) {
            // Controlla se ci sono dati OpenAPI da popolare (da lista fornitori)
            let stored_data = sessionStorage.getItem('openapi_supplier_data');
            if (stored_data) {
                let company_data = JSON.parse(stored_data);
                sessionStorage.removeItem('openapi_supplier_data');

                if (company_data.address && company_data.address.registeredOffice) {
                    OpenAPIPartyUtils.create_address_for_party(frm, company_data.address.registeredOffice, 'Supplier');
                }

                frappe.show_alert({
                    message: 'Dati OpenAPI caricati',
                    indicator: 'green'
                });
            }

            frm.add_custom_button(__('Cerca Azienda OpenAPI'), function() {
                OpenAPIPartyUtils.show_company_search_dialog(frm, 'Supplier');
            }, __("OpenAPI"));
        } else {
            frm.add_custom_button(__('Verifica con OpenAPI'), function() {
                OpenAPIPartyUtils.verify_party_data(frm, 'Supplier');
            }, __("OpenAPI"));
        }
    },

    refresh: function(frm) {
        if (frm.is_new()) {
            frm.add_custom_button(__('Cerca Azienda OpenAPI'), function() {
                OpenAPIPartyUtils.show_company_search_dialog(frm, 'Supplier');
            }, __("OpenAPI"));
        } else {
            frm.add_custom_button(__('Verifica con OpenAPI'), function() {
                OpenAPIPartyUtils.verify_party_data(frm, 'Supplier');
            }, __("OpenAPI"));
        }
    },

    before_save: function(frm) {
        OpenAPIPartyUtils.check_duplicate_tax_id(frm, 'Supplier');
    },

    after_save: function(frm) {
        OpenAPIPartyUtils.handle_after_save(frm, 'Supplier');
    }
});
