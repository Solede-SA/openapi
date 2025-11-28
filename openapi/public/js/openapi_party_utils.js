// OpenAPI Party Utils - Funzioni comuni per Customer e Supplier
// Copyright (c) 2025, OpenAPI and contributors
// For license information, please see license.txt

window.OpenAPIPartyUtils = {
    /**
     * Mostra il dialog di ricerca azienda OpenAPI
     * @param {Object} frm - Form corrente
     * @param {string} party_type - 'Customer' o 'Supplier'
     */
    show_company_search_dialog: function(frm, party_type) {
        let party_label = party_type === 'Customer' ? 'cliente' : 'fornitore';
        let storage_key = `openapi_${party_type.toLowerCase()}_data`;

        let dialog = new frappe.ui.Dialog({
            title: 'Ricerca Azienda OpenAPI',
            frm: frm,
            party_type: party_type,
            fields: [
                {
                    label: 'Tipo Ricerca',
                    fieldname: 'search_type',
                    fieldtype: 'Select',
                    options: 'Partita IVA/CF\nRagione Sociale',
                    default: 'Ragione Sociale',
                    change: function() {
                        let search_type = dialog.get_value('search_type');
                        dialog.set_df_property('search_text', 'label',
                            search_type === 'Ragione Sociale' ? 'Nome Azienda' : 'Partita IVA o Codice Fiscale'
                        );
                        dialog.set_df_property('search_text', 'description',
                            search_type === 'Ragione Sociale' ?
                            'Inserisci parte del nome (min. 3 caratteri). Usa * come wildcard' :
                            'Inserisci la partita IVA o il codice fiscale'
                        );
                    }
                },
                {
                    label: 'Nome Azienda',
                    fieldname: 'search_text',
                    fieldtype: 'Data',
                    reqd: 1,
                    description: 'Inserisci parte del nome (min. 3 caratteri). Usa * come wildcard'
                },
                {
                    fieldname: 'search_results_section',
                    fieldtype: 'Section Break',
                    label: 'Risultati Ricerca',
                    hidden: 1
                },
                {
                    fieldname: 'search_results_html',
                    fieldtype: 'HTML'
                }
            ],
            primary_action_label: 'Cerca',
            primary_action: function(values) {
                OpenAPIPartyUtils.search_companies(dialog, values, party_type);
            },
            secondary_action_label: 'Salta',
            secondary_action: function() {
                frm.doc.__openapi_skip = true;
                dialog.hide();
                frm.save();
            }
        });

        dialog.show();
    },

    /**
     * Esegue la ricerca aziende
     */
    search_companies: function(dialog, values, party_type) {
        let search_type = values.search_type;
        let search_text = values.search_text;

        if (!search_text || search_text.length < 3) {
            frappe.msgprint('Inserisci almeno 3 caratteri per la ricerca');
            return;
        }

        setTimeout(function() {
            dialog.set_value('search_text', search_text);
        }, 10);

        dialog.get_primary_btn().prop('disabled', true);
        dialog.get_primary_btn().html('<i class="fa fa-spinner fa-spin"></i> Ricerca in corso...');

        function enable_search_button() {
            dialog.get_primary_btn().prop('disabled', false);
            dialog.get_primary_btn().html('Cerca');
        }

        if (search_type === 'Ragione Sociale') {
            let filters = { companyName: search_text };

            frappe.call({
                method: "openapi.api.aziende.company_start.search_companies",
                args: { filters: filters },
                callback: function(r) {
                    enable_search_button();
                    if (r.message) {
                        if (r.message.error) {
                            frappe.msgprint({
                                title: 'Errore',
                                message: r.message.error,
                                indicator: 'red'
                            });
                        } else if (r.message.data && r.message.data.length > 0) {
                            OpenAPIPartyUtils.display_search_results(dialog, r.message.data, party_type);
                        } else {
                            frappe.msgprint('Nessuna azienda trovata');
                        }
                    }
                },
                error: function() {
                    enable_search_button();
                    frappe.msgprint({
                        title: 'Errore',
                        message: 'Errore nella ricerca',
                        indicator: 'red'
                    });
                }
            });
        } else {
            frappe.call({
                method: "openapi.api.aziende.company_start.get_company_start_data",
                args: { vat_or_tax_code: search_text },
                callback: function(r) {
                    enable_search_button();
                    if (r.message) {
                        if (r.message.error) {
                            frappe.msgprint({
                                title: 'Errore',
                                message: r.message.error,
                                indicator: 'red'
                            });
                        } else {
                            let results = [r.message];
                            OpenAPIPartyUtils.display_search_results(dialog, results, party_type);
                        }
                    }
                },
                error: function() {
                    enable_search_button();
                    frappe.msgprint({
                        title: 'Errore',
                        message: 'Errore nella ricerca',
                        indicator: 'red'
                    });
                }
            });
        }
    },

    /**
     * Mostra i risultati della ricerca
     */
    display_search_results: function(dialog, results, party_type) {
        dialog.set_df_property('search_results_section', 'hidden', 0);

        let html = `
            <div class="search-results-container">
                <h5>Trovate ${results.length} aziende:</h5>
                <div class="list-group">
        `;

        results.forEach(function(company) {
            let status_badge = '';
            if (company.activityStatus === 'CESSATA') {
                status_badge = '<span class="badge badge-danger">Cessata</span>';
            } else if (company.activityStatus === 'ATTIVA') {
                status_badge = '<span class="badge badge-success">Attiva</span>';
            }

            let addressInfo = '';
            if (company.address && company.address.registeredOffice) {
                let addr = company.address.registeredOffice;
                addressInfo = `
                    <small class="text-muted">
                        ${addr.streetName || ''} -
                        ${addr.town || ''}
                        ${addr.province ? '(' + addr.province + ')' : ''}
                    </small>
                `;
            }

            let sdiInfo = '';
            if (company.sdiCode) {
                sdiInfo = `<small class="text-info">SDI: ${company.sdiCode}</small>`;
            }

            html += `
                <a href="#" class="list-group-item list-group-item-action"
                   data-vat="${company.vatCode || company.taxCode || company.id}">
                    <div class="d-flex w-100 justify-content-between">
                        <h6 class="mb-1">${company.companyName || 'Nome non disponibile'}</h6>
                        ${status_badge}
                    </div>
                    <p class="mb-1">
                        <small>
                            ${company.vatCode ? 'P.IVA: ' + company.vatCode : ''}
                            ${company.taxCode && company.taxCode !== company.vatCode ? ' - CF: ' + company.taxCode : ''}
                        </small>
                        ${sdiInfo}
                    </p>
                    ${addressInfo}
                </a>
            `;
        });

        html += `
                </div>
            </div>
        `;

        dialog.fields_dict.search_results_html.$wrapper.html(html);

        dialog.fields_dict.search_results_html.$wrapper.find('.list-group-item').on('click', function(e) {
            e.preventDefault();
            let vat = $(this).data('vat');

            let selected_company = results.find(function(company) {
                let vatStr = String(vat);
                return (
                    String(company.vatCode) === vatStr ||
                    String(company.taxCode) === vatStr ||
                    String(company.id) === vatStr
                );
            });

            if (selected_company) {
                dialog.hide();
                let current_frm = dialog.frm || cur_frm || frappe.ui.form.cur_frm;
                OpenAPIPartyUtils.populate_party_form_from_search(current_frm, selected_company, party_type);
            }
        });
    },

    /**
     * Popola il form con i dati della ricerca
     */
    populate_party_form_from_search: function(frm, company_data, party_type) {
        if (!frm) {
            frappe.msgprint('Errore: impossibile accedere al form');
            return;
        }

        let name_field = party_type === 'Customer' ? 'customer_name' : 'supplier_name';
        let type_field = party_type === 'Customer' ? 'customer_type' : 'supplier_type';

        frm.set_value(name_field, company_data.companyName || '');

        const vat_code = company_data.vatCode || company_data.taxCode || '';
        frm.set_value('tax_id', vat_code);
        frm.set_value('fiscal_code', vat_code);
        frm.set_value(type_field, 'Company');

        if (company_data.sdiCode) {
            frm.set_value('custom_codice_univoco', company_data.sdiCode);
            frappe.show_alert({
                message: `Codice SDI impostato: ${company_data.sdiCode}`,
                indicator: 'green'
            });
        }

        if (company_data.pec) {
            frm.set_value('pec', company_data.pec);
            frappe.show_alert({
                message: `PEC impostata: ${company_data.pec}`,
                indicator: 'green'
            });
        }

        if (company_data.activityStatus === 'CESSATA') {
            frm.set_value('disabled', 1);
            frappe.msgprint({
                title: 'Attenzione',
                message: 'L\'azienda risulta CESSATA',
                indicator: 'orange'
            });
        }

        if (company_data.address && company_data.address.registeredOffice) {
            OpenAPIPartyUtils.create_address_for_party(frm, company_data.address.registeredOffice, party_type);
        }

        frappe.show_alert({
            message: 'Dati importati dalla ricerca',
            indicator: 'green'
        });
    },

    /**
     * Prepara l'indirizzo da creare dopo il salvataggio
     */
    create_address_for_party: function(frm, address_data, party_type) {
        frm.__pending_address = {
            address_line1: address_data.streetName || address_data.street || '',
            city: address_data.town || '',
            state: address_data.province || '',
            pincode: address_data.zipCode || address_data.zip || '',
            country: 'Italy',
            address_type: 'Billing',
            is_primary_address: 1,
            is_shipping_address: 0,
            party_type: party_type
        };

        frappe.show_alert({
            message: 'L\'indirizzo verrà creato dopo il salvataggio',
            indicator: 'blue'
        });
    },

    /**
     * Verifica dati party esistente con OpenAPI
     */
    verify_party_data: function(frm, party_type) {
        if (!frm.doc.tax_id) {
            let party_label = party_type === 'Customer' ? 'cliente' : 'fornitore';
            frappe.msgprint(`Il ${party_label} deve avere una partita IVA o codice fiscale per la verifica`);
            return;
        }

        frappe.show_alert({
            message: 'Verifica in corso con OpenAPI...',
            indicator: 'blue'
        });

        frappe.call({
            method: "openapi.api.aziende.company_start.verify_existing_party",
            args: {
                party_type: party_type,
                party_name: frm.doc.name
            },
            callback: function(r) {
                if (r.message) {
                    if (r.message.error) {
                        frappe.msgprint({
                            title: 'Errore',
                            message: r.message.error,
                            indicator: 'red'
                        });
                    } else if (r.message.has_differences) {
                        OpenAPIPartyUtils.show_differences_dialog(frm, r.message, party_type);
                    } else {
                        frappe.msgprint({
                            title: 'Verifica Completata',
                            message: 'I dati sono già aggiornati e corrispondono con OpenAPI',
                            indicator: 'green'
                        });
                    }
                }
            },
            error: function(r) {
                frappe.msgprint({
                    title: 'Errore di connessione',
                    message: 'Impossibile contattare il servizio OpenAPI',
                    indicator: 'red'
                });
            }
        });
    },

    /**
     * Mostra dialog con differenze trovate
     */
    show_differences_dialog: function(frm, data, party_type) {
        let fields_html = '';

        data.differences.forEach(function(diff) {
            fields_html += `
                <div class="difference-item mb-3">
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox"
                               id="update_${diff.field}" data-field='${JSON.stringify(diff)}'>
                        <label class="form-check-label" for="update_${diff.field}">
                            <strong>${diff.label}</strong><br>
                            <span class="text-muted">Attuale:</span> ${diff.current || '(vuoto)'}<br>
                            <span class="text-success">OpenAPI:</span> ${diff.openapi || '(vuoto)'}
                        </label>
                    </div>
                </div>
            `;
        });

        let dialog = new frappe.ui.Dialog({
            title: 'Differenze Trovate',
            fields: [
                {
                    fieldname: 'differences_html',
                    fieldtype: 'HTML',
                    options: `
                        <div class="differences-container">
                            <p>Seleziona i campi da aggiornare:</p>
                            ${fields_html}
                        </div>
                    `
                }
            ],
            primary_action_label: 'Aggiorna Selezionati',
            primary_action: function() {
                let fields_to_update = [];
                dialog.$wrapper.find('input[type="checkbox"]:checked').each(function() {
                    let field_data = $(this).data('field');
                    fields_to_update.push(field_data);
                });

                if (fields_to_update.length === 0) {
                    frappe.msgprint('Seleziona almeno un campo da aggiornare');
                    return;
                }

                OpenAPIPartyUtils.update_party_fields(frm, fields_to_update, party_type);
                dialog.hide();
            },
            secondary_action_label: 'Annulla'
        });

        dialog.show();
    },

    /**
     * Aggiorna i campi del party
     */
    update_party_fields: function(frm, fields_to_update, party_type) {
        frappe.call({
            method: "openapi.api.aziende.company_start.update_party_from_openapi",
            args: {
                party_type: party_type,
                party_name: frm.doc.name,
                fields_to_update: fields_to_update
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
    },

    /**
     * Gestisce il salvataggio con indirizzo pendente
     */
    handle_after_save: function(frm, party_type) {
        if (frm.__pending_address && !frm.is_new()) {
            let address = {
                doctype: 'Address',
                address_title: party_type === 'Customer' ? frm.doc.customer_name : frm.doc.supplier_name,
                address_line1: frm.__pending_address.address_line1 || '',
                city: frm.__pending_address.city || '',
                state: frm.__pending_address.state || '',
                pincode: frm.__pending_address.pincode || '',
                country: frm.__pending_address.country || 'Italy',
                address_type: 'Billing',
                is_primary_address: 1,
                is_shipping_address: 0,
                links: [{
                    link_doctype: party_type,
                    link_name: frm.doc.name
                }]
            };

            if (typeof address.state === 'object') {
                address.state = address.state.code || address.state.description || '';
            }

            let provinceWarning = null;
            if (address.state && address.state.length !== 2) {
                provinceWarning = `La provincia "${address.state}" non è nel formato standard a 2 lettere.`;
            }

            frappe.call({
                method: 'frappe.client.insert',
                args: { doc: address },
                callback: function(r) {
                    if (r.message) {
                        if (provinceWarning) {
                            frappe.show_alert({
                                message: provinceWarning,
                                indicator: 'orange'
                            }, 7);
                        } else {
                            frappe.show_alert({
                                message: 'Indirizzo creato con successo',
                                indicator: 'green'
                            });
                        }
                        frm.reload_doc();
                    }
                }
            });

            delete frm.__pending_address;
        }
    },

    /**
     * Verifica P.IVA duplicata prima del salvataggio
     */
    check_duplicate_tax_id: function(frm, party_type) {
        if (frm.doc.tax_id && !frm.doc._skip_duplicate_check) {
            let name_field = party_type === 'Customer' ? 'customer_name' : 'supplier_name';
            let party_label = party_type === 'Customer' ? 'cliente' : 'fornitore';
            let party_label_plural = party_type === 'Customer' ? 'clienti' : 'fornitori';

            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: party_type,
                    filters: {
                        'tax_id': frm.doc.tax_id,
                        'name': ['!=', frm.doc.name || 'new']
                    },
                    fields: ['name', name_field, 'tax_id']
                },
                async: false,
                callback: function(r) {
                    if (r.message && r.message.length > 0) {
                        frappe.validated = false;

                        let parties_html = '';
                        let title = r.message.length > 1
                            ? `Esistono ${r.message.length} ${party_label_plural} con questa P.IVA`
                            : `Esiste già un ${party_label} con questa P.IVA`;

                        r.message.forEach(function(party) {
                            let display_name = party[name_field];
                            parties_html += `
                                <div class="mb-2 p-2 border rounded">
                                    <strong>${display_name}</strong> (${party.name})
                                    <a href="/app/${party_type.toLowerCase()}/${party.name}" target="_blank" class="btn btn-xs btn-default pull-right">
                                        <i class="fa fa-external-link"></i> Apri
                                    </a>
                                </div>
                            `;
                        });

                        let dialog = new frappe.ui.Dialog({
                            title: 'Attenzione: P.IVA Duplicata',
                            fields: [
                                {
                                    fieldtype: 'HTML',
                                    options: `
                                        <div class="alert alert-warning">
                                            <p><strong>${title}</strong></p>
                                            <p>P.IVA: <b>${frm.doc.tax_id}</b></p>
                                        </div>
                                        <div class="mb-3">
                                            <label>${party_label_plural.charAt(0).toUpperCase() + party_label_plural.slice(1)} esistenti:</label>
                                            ${parties_html}
                                        </div>
                                        <hr>
                                        <p>Vuoi procedere comunque con l'inserimento di questo nuovo ${party_label}?</p>
                                    `
                                }
                            ],
                            primary_action_label: 'Salva comunque',
                            primary_action: function() {
                                dialog.hide();
                                frm.doc._skip_duplicate_check = true;
                                frm.save();
                            },
                            secondary_action_label: 'Annulla',
                            secondary_action: function() {
                                dialog.hide();
                            }
                        });

                        dialog.show();
                    }
                }
            });
        }
    }
};
