frappe.ui.form.on('Sales Invoice', {
    refresh: function (frm) {
        console.log(frm.doc.custom_stato_invio)

        

        if (['NS', 'EC02', 'Non Inviata', undefined].includes(frm.doc.custom_stato_invio)) {
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

        }
    }
})