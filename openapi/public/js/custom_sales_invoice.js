frappe.ui.form.on('Sales Invoice', {
    refresh: function (frm) {
        if (frm.doc.docstatus == 0 || frm.doc.docstatus == 1) {
            frm.add_custom_button(
                __("Invia a SDI OPENAPI"),
                () => {
                    frm.call({
                        method: "openapi.api.sdi.fatture.invia_fattura",
                        args: {
                            docname: frm.doc.name,
                            doctype: frm.doc.doctype,
                        },
                        callback: function (r) {
                            frm.reload_doc();
                            console.log(r);
                            if (r.message) {
                                frappe.msgprint(r.message);
                            }
                        },
                        freeze: true,
                    });
                },
                __("Fatt. Elettronica"),
            );

            console.log(frm.doc.custom_notifiche_sdi)
            if (frm.doc.custom_notifiche_sdi && frm.doc.custom_notifiche_sdi.length) {
                frm.doc.custom_notifiche_sdi.sort((a, b) => {
                    return new Date(b.data_notifica) - new Date(a.data_notifica);
                });
            }

            if (frm.doc.custom_ultima_notifica) {
                let utlima_notifica = JSON.parse(frm.doc.custom_ultima_notifica);
                console.log(utlima_notifica["data"]["notification"]);

                // Crea un div vuoto per visualizzare le notifiche
                let notificationContainer = $('<div>').appendTo(frm.fields_dict['custom_uuid'].wrapper);

                // Funzione ricorsiva per iterare attraverso l'oggetto JSON e costruire una lista puntata
                function displayNotification(data, parentElement) {
                    let ul = $('<ul>').appendTo(parentElement);
                    for (let key in data) {
                        let li = $('<li>').appendTo(ul);
                        if (typeof data[key] === 'object' && data[key] !== null) {
                            $('<strong>').text(key + ': ').appendTo(li);
                            displayNotification(data[key], li);
                        } else {
                            $('<span>').text(key + ': ' + data[key]).appendTo(li);
                        }
                    }
                }

                // Chiamata alla funzione ricorsiva
                displayNotification(utlima_notifica["data"]["notification"], notificationContainer);
            }
                

        }
    }
})