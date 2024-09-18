// Copyright (c) 2024, Solede SA and contributors
// For license information, please see license.txt

frappe.ui.form.on("Transazione SDI", {
    refresh: function (frm) {
        frm.disable_save();

        frm.set_df_property('notifiche_sdi', 'cannot_add_rows', true); // Hide add row button
        frm.set_df_property('notifiche_sdi', 'cannot_delete_rows', true); // Hide delete button
        frm.set_df_property('notifiche_sdi', 'cannot_delete_all_rows', true); // Hide delete all button
        
        if (frm.doc.notifiche_sdi && frm.doc.notifiche_sdi.length) {
            frm.doc.notifiche_sdi.sort((a, b) => {
                return new Date(b.data_notifica) - new Date(a.data_notifica);
            });
        }

        frm.add_custom_button(
            __("Scarica PDF"),
            () => {
                frm.call({
                    method: "openapi.api.sdi.fatture.download",
                    args: {
                        doctype: frm.doc.tipo_fattura,
                        docname: frm.doc.fattura,
                        type: 'pdf',
                    },
                    callback: function (r) {
                        if (r.message) {
                            let bytes = new Uint8Array(r.message);
                            const blob = new Blob([bytes], { type: 'application/pdf' });
                            const url = URL.createObjectURL(blob);

                            // Crea un elemento link e avvia il download
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `${frm.doc.fattura}.pdf`;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);

                            // Revoca l'URL dell'oggetto dopo il download
                            URL.revokeObjectURL(url);
                        }
                    },
                    freeze: true,
                });
            }
        );

        if (frm.doc.ultima_notifica) {
            let utlima_notifica = JSON.parse(frm.doc.ultima_notifica);

            // Crea un div vuoto per visualizzare le notifiche
            let notificationContainer = $('<div>').appendTo(frm.fields_dict['uuid'].wrapper);

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
});

