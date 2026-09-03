frappe.ui.form.on('Sales Invoice', {
    refresh: function (frm) {
        // Chiama un metodo SDI, ricarica il documento e mostra il messaggio di risposta
        // (o un handler custom, per i casi in cui il messaggio non è testo semplice).
        function call_sdi_action(method, args, on_message) {
            frm.call({
                method: method,
                args: args,
                callback: function (r) {
                    frm.reload_doc();
                    if (r.message) {
                        (on_message || frappe.msgprint)(r.message);
                    }
                },
                freeze: true,
            });
        }

        // Solo fatture confermate: una bozza può avere un nome provvisorio (BOZZA-…).
        if (frm.doc.docstatus === 1 && ['NS', 'EC02', 'Non Inviata', undefined].includes(frm.doc.custom_stato_invio)) {
            frm.add_custom_button(
                __("Invia a Sistema di Interscambio"),
                () => call_sdi_action("openapi.api.sdi.fatture.invia_fattura", {
                    docname: frm.doc.name,
                    doctype: frm.doc.doctype,
                }),
                __("Fatt. Elettronica"),
            );
        }

        if (frappe.user.has_role("System Manager") && frm.doc.custom_transazione_sdi) {
            frm.add_custom_button(
                __("Verifica stato reale su SDI"),
                () => call_sdi_action(
                    "openapi.api.sdi.fatture.verifica_stato_sdi",
                    { docname: frm.doc.name, doctype: frm.doc.doctype },
                    (message) => frappe.msgprint({
                        title: __("Verifica stato SDI"),
                        message: __("Stato precedente: {0}<br>Stato nuovo: {1}", [
                            message.stato_precedente,
                            message.stato_nuovo,
                        ]),
                        indicator: "blue",
                    })
                ),
                __("Emergenza SDI"),
            );

            frm.add_custom_button(
                __("Forza reinvio a SDI"),
                () => {
                    frappe.prompt(
                        {
                            fieldname: "motivo",
                            label: __("Motivo del reinvio di emergenza"),
                            fieldtype: "Small Text",
                            reqd: 1,
                        },
                        (values) => {
                            frappe.confirm(
                                __("Attenzione: se SDI ha già ricevuto questa fattura, il reinvio genera una trasmissione duplicata. Procedere solo se confermato (es. con \"Verifica stato reale su SDI\") che la trasmissione precedente non è mai arrivata a SDI. Continuare?"),
                                () => call_sdi_action("openapi.api.sdi.fatture.forza_reinvio_sdi", {
                                    docname: frm.doc.name,
                                    doctype: frm.doc.doctype,
                                    motivo: values.motivo,
                                })
                            );
                        },
                        __("Forza reinvio a SDI"),
                        __("Conferma reinvio")
                    );
                },
                __("Emergenza SDI"),
            );
        }

        if (frm.doc.custom_uuid) {
            frm.add_custom_button(
            __("Scarica PDF"),
            () => {
                let url = "/api/method/openapi.api.sdi.fatture.download?doctype=" + frm.doc.doctype + "&docname=" + frm.doc.name + "&type=pdf";
                // window.open(url);
                window.location.href = url
                },
            __("Fatt. Elettronica"),
            );
        }
    }
})