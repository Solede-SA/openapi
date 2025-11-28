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
