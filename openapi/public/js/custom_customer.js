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
    }

    // Pulsanti per Individual (persona fisica)
    if (frm.doc.customer_type === 'Individual') {
        let fiscal_code = frm.doc.fiscal_code || frm.doc.tax_id;

        // Se c'è una verifica in corso, mostra "Controlla Stato"
        if (frm.doc.custom_negativita_status === 'In Elaborazione' && frm.doc.custom_negativita_request_id) {
            frm.add_custom_button(__('Controlla Stato Negatività'), function() {
                check_negativita_status(frm);
            }, __("OpenAPI"));
        }

        // Pulsante verifica negatività (solo se ha CF persona fisica)
        if (fiscal_code && fiscal_code.length === 16) {
            frm.add_custom_button(__('Verifica Negatività'), function() {
                request_negativita_check(frm);
            }, __("OpenAPI"));
        }
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
                    show_credit_score_dialog(frm, r.message);
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

function show_credit_score_dialog(frm, data) {
    // Determina il colore del badge in base al rating
    let rating_color = get_rating_color(data.rating);
    let risk_color = get_risk_color(data.risk_score);

    // Formatta il credit limit
    let credit_limit = data.operational_credit_limit
        ? format_currency(data.operational_credit_limit)
        : 'N/D';

    let html = `
        <div class="credit-score-container">
            <div class="row mb-4">
                <div class="col-md-6 text-center">
                    <h5>Rating</h5>
                    <span class="badge" style="font-size: 2em; background-color: ${rating_color}; color: white; padding: 15px 25px;">
                        ${data.rating || 'N/D'}
                    </span>
                </div>
                <div class="col-md-6 text-center">
                    <h5>Risk Score</h5>
                    <span class="badge" style="font-size: 1.5em; background-color: ${risk_color}; color: white; padding: 10px 20px;">
                        ${data.risk_score || 'N/D'}
                    </span>
                </div>
            </div>

            <div class="row mb-3">
                <div class="col-12">
                    <div class="alert alert-${get_alert_class(data.rating)}">
                        <strong>Descrizione Rischio:</strong> ${data.risk_score_description || 'N/D'}
                    </div>
                </div>
            </div>

            <table class="table table-bordered">
                <tbody>
                    <tr>
                        <th style="width: 40%;">Limite di Credito Operativo</th>
                        <td><strong>${credit_limit}</strong></td>
                    </tr>
                    <tr>
                        <th>Indice di Rischio (1-990)</th>
                        <td>${data.risk_severity || 'N/D'}</td>
                    </tr>
                    <tr>
                        <th>Ragione Sociale</th>
                        <td>${data.organization_name || 'N/D'}</td>
                    </tr>
                    <tr>
                        <th>P.IVA</th>
                        <td>${data.vat || 'N/D'}</td>
                    </tr>
                    <tr>
                        <th>Codice Fiscale</th>
                        <td>${data.tax || 'N/D'}</td>
                    </tr>
                </tbody>
            </table>

            <p class="text-muted small">
                Dati aggiornati al: ${data.requested_at || 'N/D'}
            </p>
        </div>
    `;

    let dialog = new frappe.ui.Dialog({
        title: 'Verifica Creditizia - ' + frm.doc.customer_name,
        fields: [
            {
                fieldname: 'credit_score_html',
                fieldtype: 'HTML',
                options: html
            }
        ],
        primary_action_label: 'Salva nel Cliente',
        primary_action: function() {
            save_credit_score(frm, data);
            dialog.hide();
        },
        secondary_action_label: 'Chiudi'
    });

    dialog.show();
    dialog.$wrapper.find('.modal-dialog').css('max-width', '600px');
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

function get_rating_color(rating) {
    if (!rating) return '#6c757d';

    // Rating A1-A3: Verde (basso rischio)
    // Rating B1-B3: Giallo/Arancione (medio rischio)
    // Rating C1-C3: Rosso (alto rischio)
    if (rating.startsWith('A')) {
        if (rating === 'A1') return '#28a745';
        if (rating === 'A2') return '#5cb85c';
        if (rating === 'A3') return '#8bc34a';
    }
    if (rating.startsWith('B')) {
        if (rating === 'B1') return '#ffc107';
        if (rating === 'B2') return '#ff9800';
        if (rating === 'B3') return '#ff5722';
    }
    if (rating.startsWith('C')) {
        if (rating === 'C1') return '#f44336';
        if (rating === 'C2') return '#d32f2f';
        if (rating === 'C3') return '#b71c1c';
    }
    return '#6c757d';
}

function get_risk_color(risk_score) {
    if (!risk_score) return '#6c757d';

    // Mappa i colori del risk score
    const colors = {
        'Verde': '#28a745',
        'Verde Chiaro': '#8bc34a',
        'Giallo': '#ffc107',
        'Arancione': '#ff9800',
        'Arancione Scuro': '#ff5722',
        'Rosso': '#f44336',
        'Rosso Scuro': '#b71c1c'
    };

    return colors[risk_score] || '#6c757d';
}

function get_alert_class(rating) {
    if (!rating) return 'secondary';

    if (rating.startsWith('A')) return 'success';
    if (rating.startsWith('B')) return 'warning';
    if (rating.startsWith('C')) return 'danger';

    return 'secondary';
}

function format_currency(value) {
    if (!value) return 'N/D';
    return new Intl.NumberFormat('it-IT', {
        style: 'currency',
        currency: 'EUR'
    }).format(value);
}

// ==================== VERIFICA NEGATIVITÀ (Individual) ====================

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
                        show_negativita_result(frm, r.message.details);
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

function show_negativita_result(frm, data) {
    let protesti = data.protesti || [];
    let pregiudizievoli = data.pregiudizievoli || [];
    let procedure = data.procedure_concorsuali || [];

    let total = protesti.length + pregiudizievoli.length + procedure.length;
    let status_color = total === 0 ? '#28a745' : '#dc3545';
    let status_text = total === 0 ? 'Nessuna negatività' : `Trovate ${total} negatività`;

    let html = `
        <div class="negativita-container">
            <div class="text-center mb-4">
                <span class="badge" style="font-size: 1.5em; background-color: ${status_color}; color: white; padding: 10px 20px;">
                    ${status_text}
                </span>
            </div>

            <table class="table table-bordered">
                <tbody>
                    <tr>
                        <th style="width: 50%;">Protesti</th>
                        <td><strong>${protesti.length}</strong></td>
                    </tr>
                    <tr>
                        <th>Pregiudizievoli</th>
                        <td><strong>${pregiudizievoli.length}</strong></td>
                    </tr>
                    <tr>
                        <th>Procedure Concorsuali</th>
                        <td><strong>${procedure.length}</strong></td>
                    </tr>
                </tbody>
            </table>
    `;

    // Mostra dettagli protesti se presenti
    if (protesti.length > 0) {
        html += `
            <h5 class="mt-4">Dettaglio Protesti</h5>
            <table class="table table-sm table-striped">
                <thead>
                    <tr>
                        <th>Data</th>
                        <th>Importo</th>
                        <th>Tipo</th>
                    </tr>
                </thead>
                <tbody>
        `;
        protesti.forEach(p => {
            html += `
                <tr>
                    <td>${p.data || 'N/D'}</td>
                    <td>${p.importo ? format_currency(p.importo) : 'N/D'}</td>
                    <td>${p.tipo || 'N/D'}</td>
                </tr>
            `;
        });
        html += `</tbody></table>`;
    }

    // Mostra dettagli pregiudizievoli se presenti
    if (pregiudizievoli.length > 0) {
        html += `
            <h5 class="mt-4">Dettaglio Pregiudizievoli</h5>
            <table class="table table-sm table-striped">
                <thead>
                    <tr>
                        <th>Data</th>
                        <th>Tipo</th>
                        <th>Descrizione</th>
                    </tr>
                </thead>
                <tbody>
        `;
        pregiudizievoli.forEach(p => {
            html += `
                <tr>
                    <td>${p.data || 'N/D'}</td>
                    <td>${p.tipo || 'N/D'}</td>
                    <td>${p.descrizione || 'N/D'}</td>
                </tr>
            `;
        });
        html += `</tbody></table>`;
    }

    // Mostra dettagli procedure concorsuali se presenti
    if (procedure.length > 0) {
        html += `
            <h5 class="mt-4">Dettaglio Procedure Concorsuali</h5>
            <table class="table table-sm table-striped">
                <thead>
                    <tr>
                        <th>Data</th>
                        <th>Tipo</th>
                        <th>Tribunale</th>
                    </tr>
                </thead>
                <tbody>
        `;
        procedure.forEach(p => {
            html += `
                <tr>
                    <td>${p.data || 'N/D'}</td>
                    <td>${p.tipo || 'N/D'}</td>
                    <td>${p.tribunale || 'N/D'}</td>
                </tr>
            `;
        });
        html += `</tbody></table>`;
    }

    html += `</div>`;

    let dialog = new frappe.ui.Dialog({
        title: 'Verifica Negatività - ' + frm.doc.customer_name,
        fields: [
            {
                fieldname: 'negativita_html',
                fieldtype: 'HTML',
                options: html
            }
        ],
        primary_action_label: 'Chiudi'
    });

    dialog.show();
    dialog.$wrapper.find('.modal-dialog').css('max-width', '700px');
}
