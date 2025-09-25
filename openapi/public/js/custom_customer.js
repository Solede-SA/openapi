
frappe.ui.form.on('Customer', {
    onload: function(frm) {
        // Controlla se ci sono dati OpenAPI da popolare (da lista clienti)
        if (frm.is_new()) {
            let stored_data = sessionStorage.getItem('openapi_customer_data');
            if (stored_data) {
                let company_data = JSON.parse(stored_data);
                sessionStorage.removeItem('openapi_customer_data'); // Pulisci dopo l'uso

                // Gestisci l'indirizzo se presente
                if (company_data.address && company_data.address.registeredOffice) {
                    let addr = company_data.address.registeredOffice;
                    create_address_for_customer(frm, addr);
                }

                frappe.show_alert({
                    message: 'Dati OpenAPI caricati',
                    indicator: 'green'
                });
            }

            // Aggiungi pulsante per nuovi clienti
            frm.add_custom_button(__('Cerca Azienda OpenAPI'), function() {
                show_company_search_dialog(frm);
            }, __("OpenAPI"));
        } else {
            // Aggiungi pulsante per clienti esistenti
            frm.add_custom_button(__('Verifica con OpenAPI'), function() {
                verify_customer_data(frm);
            }, __("OpenAPI"));
        }
    },

    refresh: function(frm) {
        // Refresh dei pulsanti anche al refresh del form
        if (frm.is_new()) {
            frm.add_custom_button(__('Cerca Azienda OpenAPI'), function() {
                show_company_search_dialog(frm);
            }, __("OpenAPI"));
        } else {
            frm.add_custom_button(__('Verifica con OpenAPI'), function() {
                verify_customer_data(frm);
            }, __("OpenAPI"));
        }
    },

    before_save: function(frm) {
        // Verifica P.IVA duplicata prima del salvataggio
        if (frm.doc.tax_id && !frm.doc._skip_duplicate_check) {
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Customer',
                    filters: {
                        'tax_id': frm.doc.tax_id,
                        'name': ['!=', frm.doc.name || 'new']
                    },
                    fields: ['name', 'customer_name', 'tax_id']
                },
                async: false,  // Sincrono per bloccare il salvataggio
                callback: function(r) {
                    if (r.message && r.message.length > 0) {
                        frappe.validated = false;  // Blocca temporaneamente il salvataggio

                        let customers_html = '';
                        let title = r.message.length > 1
                            ? `Esistono ${r.message.length} clienti con questa P.IVA`
                            : 'Esiste già un cliente con questa P.IVA';

                        // Crea la lista dei clienti esistenti
                        r.message.forEach(function(customer) {
                            customers_html += `
                                <div class="mb-2 p-2 border rounded">
                                    <strong>${customer.customer_name}</strong> (${customer.name})
                                    <a href="/app/customer/${customer.name}" target="_blank" class="btn btn-xs btn-default pull-right">
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
                                            <label>Clienti esistenti:</label>
                                            ${customers_html}
                                        </div>
                                        <hr>
                                        <p>Vuoi procedere comunque con l'inserimento di questo nuovo cliente?</p>
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
});

function show_company_search_dialog(frm) {
    let dialog = new frappe.ui.Dialog({
        title: 'Ricerca Azienda OpenAPI',
        frm: frm,  // Salva il riferimento al frm nel dialog
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
            search_companies(dialog, values);
        },
        secondary_action_label: 'Salta',
        secondary_action: function() {
            frm.doc.__openapi_skip = true;
            dialog.hide();
            frm.save();
        }
    });

    dialog.show();
}

function search_companies(dialog, values) {
    let search_type = values.search_type;
    let search_text = values.search_text;

    if (!search_text || search_text.length < 3) {
        frappe.msgprint('Inserisci almeno 3 caratteri per la ricerca');
        return;
    }

    // Reimposta il valore nel campo (Frappe lo pulisce automaticamente dopo primary_action)
    setTimeout(function() {
        dialog.set_value('search_text', search_text);
    }, 10);

    // Disabilita il pulsante di ricerca e mostra feedback visivo
    dialog.get_primary_btn().prop('disabled', true);
    dialog.get_primary_btn().html('<i class="fa fa-spinner fa-spin"></i> Ricerca in corso...');

    // Funzione per riabilitare il pulsante
    function enable_search_button() {
        dialog.get_primary_btn().prop('disabled', false);
        dialog.get_primary_btn().html('Cerca');
    }

    if (search_type === 'Ragione Sociale') {
        // Per nome usa IT-search
        let filters = {
            companyName: search_text
        };

        frappe.call({
            method: "openapi.api.aziende.company_start.search_companies",
            args: { filters: filters },
            callback: function(r) {
                enable_search_button(); // Riabilita il pulsante

                console.log('=== RISPOSTA API SEARCH ===');
                console.log('Filters:', filters);
                console.log('Response:', r.message);

                if (r.message) {
                    if (r.message.error) {
                        frappe.msgprint({
                            title: 'Errore',
                            message: r.message.error,
                            indicator: 'red'
                        });
                    } else if (r.message.data && r.message.data.length > 0) {
                        console.log('AZIENDE TROVATE (con sdiCode):', r.message.data);
                        display_search_results(dialog, r.message.data);
                    } else {
                        frappe.msgprint('Nessuna azienda trovata');
                    }
                }
            },
            error: function() {
                enable_search_button(); // Riabilita anche in caso di errore
                frappe.msgprint({
                    title: 'Errore',
                    message: 'Errore nella ricerca',
                    indicator: 'red'
                });
            }
        });
    } else {
        // Per P.IVA/CF usa IT-start direttamente
        frappe.call({
            method: "openapi.api.aziende.company_start.get_company_start_data",
            args: { vat_or_tax_code: search_text },
            callback: function(r) {
                enable_search_button(); // Riabilita il pulsante

                console.log('=== RISPOSTA IT-START ===');
                console.log('Response:', r.message);

                if (r.message) {
                    if (r.message.error) {
                        frappe.msgprint({
                            title: 'Errore',
                            message: r.message.error,
                            indicator: 'red'
                        });
                    } else {
                        // IT-start restituisce un singolo risultato, mettiamolo in un array per display_search_results
                        let results = [r.message];
                        console.log('AZIENDA TROVATA (con sdiCode):', results);
                        display_search_results(dialog, results);
                    }
                }
            },
            error: function() {
                enable_search_button(); // Riabilita anche in caso di errore
                frappe.msgprint({
                    title: 'Errore',
                    message: 'Errore nella ricerca',
                    indicator: 'red'
                });
            }
        });
    }
}

function display_search_results(dialog, results) {
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

        // Gestisci l'indirizzo correttamente
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

        // Mostra codice SDI se presente
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

    // Aggiungi event handler per i click
    dialog.fields_dict.search_results_html.$wrapper.find('.list-group-item').on('click', function(e) {
        e.preventDefault();
        let vat = $(this).data('vat');

        console.log('=== CLICK SU AZIENDA ===');
        console.log('VAT cliccato (data-vat):', vat);
        console.log('Tipo di vat:', typeof vat);
        console.log('Results disponibili:', results);

        // Trova i dati dell'azienda selezionata dai risultati della ricerca
        let selected_company = results.find(function(company) {
            // Converti a stringa per sicurezza nel confronto
            let vatStr = String(vat);
            let matches = (
                String(company.vatCode) === vatStr ||
                String(company.taxCode) === vatStr ||
                String(company.id) === vatStr
            );
            console.log(`Confronto - vatCode: ${company.vatCode}, taxCode: ${company.taxCode}, id: ${company.id} === ${vatStr} ? ${matches}`);
            return matches;
        });

        console.log('Azienda selezionata:', selected_company);

        if (selected_company) {
            console.log('✅ Popolo form con dati ricerca (incluso sdiCode):', selected_company.sdiCode);

            // Chiudi il dialog prima di popolare il form
            dialog.hide();

            // Ottieni il form corretto
            let current_frm = dialog.frm || cur_frm || frappe.ui.form.cur_frm;

            // POPOLA DIRETTAMENTE IL FORM - NIENTE CHIAMATE SERVER
            populate_customer_form_from_search(current_frm, selected_company);
        } else {
            console.error('❌ Azienda non trovata nei risultati');
            console.error('VAT cercato:', vat);
            console.error('VATs disponibili:', results.map(r => ({vatCode: r.vatCode, taxCode: r.taxCode, id: r.id})));
        }
    });
}

// FUNZIONE RIMOSSA - Non serve più, usiamo sempre display_search_results

// FUNZIONE RIMOSSA - Non serve più, usiamo solo populate_customer_form_from_search

function populate_customer_form_from_search(frm, company_data) {
    console.log('=== POPULATE FROM SEARCH DATA (NO API CALL) ===');
    console.log('Frm object:', frm);
    console.log('Company data from search:', company_data);
    console.log('SDI Code presente nei dati ricerca:', company_data.sdiCode);

    // Verifica che frm esista
    if (!frm) {
        console.error('❌ FRM non disponibile!');
        frappe.msgprint('Errore: impossibile accedere al form del cliente');
        return;
    }

    // USA DIRETTAMENTE I DATI DELLA RICERCA - NON FARE ALTRE CHIAMATE API!
    console.log('Impostando customer_name:', company_data.companyName);
    frm.set_value('customer_name', company_data.companyName || '');

    console.log('Impostando tax_id:', company_data.vatCode || company_data.taxCode);
    frm.set_value('tax_id', company_data.vatCode || company_data.taxCode || '');

    console.log('Impostando customer_type: Company');
    frm.set_value('customer_type', 'Company');

    // IMPOSTA IL CODICE SDI DALLA RICERCA
    if (company_data.sdiCode) {
        console.log('Impostando custom_codice_univoco:', company_data.sdiCode);
        frm.set_value('custom_codice_univoco', company_data.sdiCode);
        frappe.show_alert({
            message: `Codice SDI impostato: ${company_data.sdiCode}`,
            indicator: 'green'
        });
    } else {
        console.log('⚠️ SDI Code non presente nei dati della ricerca');
    }

    // IMPOSTA LA PEC DALLA RICERCA
    if (company_data.pec) {
        console.log('Impostando custom_pec:', company_data.pec);
        frm.set_value('custom_pec', company_data.pec);
        frappe.show_alert({
            message: `PEC impostata: ${company_data.pec}`,
            indicator: 'green'
        });
    } else {
        console.log('⚠️ PEC non presente nei dati della ricerca');
    }

    // Gestisci stato azienda
    if (company_data.activityStatus === 'CESSATA') {
        frm.set_value('disabled', 1);
        frappe.msgprint({
            title: 'Attenzione',
            message: 'L\'azienda risulta CESSATA',
            indicator: 'orange'
        });
    }

    // Gestisci l'indirizzo se disponibile
    if (company_data.address && company_data.address.registeredOffice) {
        create_address_for_customer(frm, company_data.address.registeredOffice);
    }

    frappe.show_alert({
        message: 'Dati importati dalla ricerca (senza chiamate API aggiuntive)',
        indicator: 'green'
    });
}

// FUNZIONI RIMOSSE - Non servono più, usiamo solo i dati della ricerca

function create_address_for_customer(frm, address_data) {
    // Nota: l'indirizzo verrà creato dopo il salvataggio del cliente
    frm.__pending_address = {
        address_line1: address_data.streetName || address_data.street || '',
        city: address_data.town || '',
        state: address_data.province || '',
        pincode: address_data.zipCode || address_data.zip || '',
        country: 'Italy',
        address_type: 'Billing',
        is_primary_address: 1,
        is_shipping_address: 0
    };

    frappe.show_alert({
        message: 'L\'indirizzo verrà creato dopo il salvataggio',
        indicator: 'blue'
    });
}

function verify_customer_data(frm) {
    if (!frm.doc.tax_id) {
        frappe.msgprint('Il cliente deve avere una partita IVA o codice fiscale per la verifica');
        return;
    }

    // Non usiamo frappe.show_progress che sembra avere problemi
    frappe.show_alert({
        message: 'Verifica in corso con OpenAPI...',
        indicator: 'blue'
    });

    frappe.call({
        method: "openapi.api.aziende.company_start.verify_existing_customer",
        args: { customer_name: frm.doc.name },
        callback: function(r) {
            if (r.message) {
                if (r.message.error) {
                    frappe.msgprint({
                        title: 'Errore',
                        message: r.message.error,
                        indicator: 'red'
                    });
                } else if (r.message.has_differences) {
                    show_differences_dialog(frm, r.message);
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
}

function show_differences_dialog(frm, data) {
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

            update_customer_fields(frm, fields_to_update);
            dialog.hide();
        },
        secondary_action_label: 'Annulla'
    });

    dialog.show();
}

function update_customer_fields(frm, fields_to_update) {
    frappe.call({
        method: "openapi.api.aziende.company_start.update_customer_from_openapi",
        args: {
            customer_name: frm.doc.name,
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
}

// Gestione salvataggio con indirizzo pendente
frappe.ui.form.on('Customer', {
    after_save: function(frm) {
        if (frm.__pending_address && !frm.is_new()) {
            // Crea l'indirizzo dopo il salvataggio del cliente
            let address = {
                doctype: 'Address',
                address_title: frm.doc.customer_name,
                address_line1: frm.__pending_address.address_line1 || '',
                city: frm.__pending_address.city || '',
                state: frm.__pending_address.state || '',  // Assicurati che sia una stringa
                pincode: frm.__pending_address.pincode || '',
                country: frm.__pending_address.country || 'Italy',
                address_type: 'Billing',
                is_primary_address: 1,
                is_shipping_address: 0,
                links: [{
                    link_doctype: 'Customer',
                    link_name: frm.doc.name
                }]
            };

            // Assicurati che state sia una stringa, non un dict
            if (typeof address.state === 'object') {
                address.state = address.state.code || address.state.description || '';
            }

            frappe.call({
                method: 'frappe.client.insert',
                args: { doc: address },
                callback: function(r) {
                    if (r.message) {
                        frappe.show_alert({
                            message: 'Indirizzo creato con successo',
                            indicator: 'green'
                        });
                        // Ricarica il form per vedere l'indirizzo collegato automaticamente dall'hook
                        frm.reload_doc();
                    }
                }
            });

            delete frm.__pending_address;
        }
    }
});