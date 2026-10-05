// Custom Customer JS - Integrazione OpenAPI
// Copyright (c) 2025, OpenAPI and contributors
// For license information, please see license.txt

frappe.ui.form.on('Customer', {
    onload: function(frm) {
        if (frm.is_new()) {
            // Controlla se ci sono dati OpenAPI da popolare (da lista clienti)
            let stored_data = sessionStorage.getItem('openapi_customer_data');
            if (stored_data) {
                let company_data = JSON.parse(stored_data);
                sessionStorage.removeItem('openapi_customer_data');

                if (company_data.address && company_data.address.registeredOffice) {
                    OpenAPIPartyUtils.create_address_for_party(frm, company_data.address.registeredOffice, 'Customer');
                }

                frappe.show_alert({
                    message: 'Dati OpenAPI caricati',
                    indicator: 'green'
                });
            }

            frm.add_custom_button(__('Cerca Azienda OpenAPI'), function() {
                OpenAPIPartyUtils.show_company_search_dialog(frm, 'Customer');
            }, __("OpenAPI"));
        } else {
            add_openapi_buttons(frm);
        }
    },

    refresh: function(frm) {
        if (frm.is_new()) {
            frm.add_custom_button(__('Cerca Azienda OpenAPI'), function() {
                OpenAPIPartyUtils.show_company_search_dialog(frm, 'Customer');
            }, __("OpenAPI"));
        } else {
            add_openapi_buttons(frm);
        }
    },

    before_save: function(frm) {
        OpenAPIPartyUtils.check_duplicate_tax_id(frm, 'Customer');
    },

    after_save: function(frm) {
        OpenAPIPartyUtils.handle_after_save(frm, 'Customer');
    }
});

function add_openapi_buttons(frm) {
    // Pulsante verifica dati anagrafici
    frm.add_custom_button(__('Verifica Anagrafica'), function() {
        OpenAPIPartyUtils.verify_party_data(frm, 'Customer');
    }, __("OpenAPI"));

    // Pulsante verifica creditizia (solo per Company con P.IVA)
    if (frm.doc.customer_type === 'Company' && frm.doc.tax_id) {
        frm.add_custom_button(__('Verifica Creditizia'), function() {
            get_customer_credit_score(frm);
        }, __("OpenAPI"));

        frm.add_custom_button(__('Dati Bilancio'), function() {
            get_customer_bilancio(frm);
        }, __("OpenAPI"));
    }

    // Verifica negatività: persona fisica con codice fiscale, azienda con partita IVA
    if (frm.doc.custom_negativita_status === 'In Elaborazione' && frm.doc.custom_negativita_request_id) {
        frm.add_custom_button(__('Controlla Stato Negatività'), function() {
            check_negativita_status(frm);
        }, __("OpenAPI"));
    }

    // Il formato del codice lo controlla il server
    if (frm.doc.fiscal_code || frm.doc.tax_id) {
        frm.add_custom_button(__('Verifica Negatività'), function() {
            request_negativita_check(frm);
        }, __("OpenAPI"));
    }

    if (frm.doc.custom_negativita_status === 'Completata') {
        frm.add_custom_button(__('Vedi Negatività'), function() {
            openapi.credit_check.show_negativita(JSON.parse(frm.doc.custom_negativita_dettagli), 'Verifica Negatività - ' + frm.doc.customer_name);
        }, __("OpenAPI"));
    }
}

function get_customer_credit_score(frm) {
    frappe.show_alert({
        message: 'Verifica creditizia in corso...',
        indicator: 'blue'
    });

    frappe.call({
        method: "openapi.api.aziende.credit_scoring.get_customer_credit_score",
        args: { customer_name: frm.doc.name },
        callback: function(r) {
            if (r.message) {
                if (r.message.error) {
                    frappe.msgprint({
                        title: 'Errore',
                        message: r.message.error,
                        indicator: 'red'
                    });
                } else {
                    openapi.credit_check.show_score(r.message, {
                        title: 'Verifica Creditizia - ' + frm.doc.customer_name,
                        on_save: () => save_credit_score(frm, r.message),
                    });
                }
            }
        },
        error: function() {
            frappe.msgprint({
                title: 'Errore di connessione',
                message: 'Impossibile contattare il servizio OpenAPI',
                indicator: 'red'
            });
        }
    });
}

function save_credit_score(frm, data) {
    frappe.call({
        method: "openapi.api.aziende.credit_scoring.save_credit_score_to_customer",
        args: {
            customer_name: frm.doc.name,
            credit_data: data
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                frappe.show_alert({
                    message: r.message.message,
                    indicator: 'green'
                });
                frm.reload_doc();
            }
        }
    });
}

// ==================== VERIFICA NEGATIVITÀ ====================

function request_negativita_check(frm) {
    frappe.show_alert({
        message: 'Invio richiesta verifica negatività...',
        indicator: 'blue'
    });

    frappe.call({
        method: "openapi.api.aziende.negativita_persona.get_customer_negativita",
        args: { customer_name: frm.doc.name },
        callback: function(r) {
            if (r.message) {
                if (r.message.error) {
                    frappe.msgprint({
                        title: 'Errore',
                        message: r.message.error,
                        indicator: 'red'
                    });
                } else if (r.message.success) {
                    frappe.show_alert({
                        message: r.message.message,
                        indicator: 'green'
                    });
                    frm.reload_doc();
                }
            }
        },
        error: function() {
            frappe.msgprint({
                title: 'Errore di connessione',
                message: 'Impossibile contattare il servizio OpenAPI',
                indicator: 'red'
            });
        }
    });
}

function check_negativita_status(frm) {
    frappe.show_alert({
        message: 'Controllo stato verifica...',
        indicator: 'blue'
    });

    frappe.call({
        method: "openapi.api.aziende.negativita_persona.check_customer_negativita_status",
        args: { customer_name: frm.doc.name },
        callback: function(r) {
            if (r.message) {
                if (r.message.error) {
                    frappe.msgprint({
                        title: 'Errore',
                        message: r.message.error,
                        indicator: 'red'
                    });
                } else if (r.message.success) {
                    if (r.message.status === 'COMPLETED' && r.message.details) {
                        openapi.credit_check.show_negativita(r.message.details, 'Verifica Negatività - ' + frm.doc.customer_name);
                    } else {
                        frappe.show_alert({
                            message: 'Verifica ancora in elaborazione. Riprova tra qualche minuto.',
                            indicator: 'orange'
                        });
                    }
                    frm.reload_doc();
                }
            }
        },
        error: function() {
            frappe.msgprint({
                title: 'Errore di connessione',
                message: 'Impossibile contattare il servizio OpenAPI',
                indicator: 'red'
            });
        }
    });
}

// ==================== DATI BILANCIO (Company) ====================

function get_customer_bilancio(frm) {
    frappe.show_alert({
        message: 'Recupero dati bilancio in corso...',
        indicator: 'blue'
    });

    frappe.call({
        method: "openapi.api.aziende.company_start.get_customer_bilancio",
        args: { customer_name: frm.doc.name },
        callback: function(r) {
            if (r.message) {
                if (r.message.error) {
                    frappe.msgprint({
                        title: 'Errore',
                        message: r.message.error,
                        indicator: 'red'
                    });
                } else if (r.message.success) {
                    show_bilancio_dialog(frm, r.message.bilancio, r.message.full_data);
                }
            }
        },
        error: function() {
            frappe.msgprint({
                title: 'Errore di connessione',
                message: 'Impossibile contattare il servizio OpenAPI',
                indicator: 'red'
            });
        }
    });
}

function show_bilancio_dialog(frm, bilancio, full_data) {
    let fatturato = bilancio.fatturato ? format_currency(bilancio.fatturato, "EUR") : 'N/D';
    let patrimonio_netto = bilancio.patrimonio_netto ? format_currency(bilancio.patrimonio_netto, "EUR") : 'N/D';
    let dipendenti = bilancio.dipendenti !== null ? bilancio.dipendenti : 'N/D';
    let anno = bilancio.anno_bilancio || 'N/D';

    let html = `
        <div class="bilancio-container">
            <div class="row mb-4">
                <div class="col-md-6 text-center">
                    <h5>Fatturato</h5>
                    <span class="badge" style="font-size: 1.5em; background-color: #007bff; color: white; padding: 10px 20px;">
                        ${fatturato}
                    </span>
                </div>
                <div class="col-md-6 text-center">
                    <h5>Patrimonio Netto</h5>
                    <span class="badge" style="font-size: 1.5em; background-color: #17a2b8; color: white; padding: 10px 20px;">
                        ${patrimonio_netto}
                    </span>
                </div>
            </div>

            <table class="table table-bordered">
                <tbody>
                    <tr>
                        <th style="width: 40%;">Numero Dipendenti</th>
                        <td><strong>${dipendenti}</strong></td>
                    </tr>
                    <tr>
                        <th>Anno Bilancio</th>
                        <td>${anno}</td>
                    </tr>
                </tbody>
            </table>

            <p class="text-muted small mt-3">
                I dati sono forniti da OpenAPI.it e si riferiscono all'ultimo bilancio disponibile.
            </p>
        </div>
    `;

    let dialog = new frappe.ui.Dialog({
        title: 'Dati Bilancio - ' + frm.doc.customer_name,
        fields: [
            {
                fieldname: 'bilancio_html',
                fieldtype: 'HTML',
                options: html
            }
        ],
        primary_action_label: 'Salva nel Cliente',
        primary_action: function() {
            save_bilancio(frm, bilancio, full_data);
            dialog.hide();
        },
        secondary_action_label: 'Chiudi'
    });

    dialog.show();
    dialog.$wrapper.find('.modal-dialog').css('max-width', '500px');
}

function save_bilancio(frm, bilancio, full_data) {
    frappe.call({
        method: "openapi.api.aziende.company_start.save_bilancio_to_customer",
        args: {
            customer_name: frm.doc.name,
            bilancio_data: bilancio,
            full_data: full_data
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                frappe.show_alert({
                    message: r.message.message,
                    indicator: 'green'
                });
                frm.reload_doc();
            }
        }
    });
}
