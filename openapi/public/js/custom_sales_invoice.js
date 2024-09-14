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
                    });
                },
                __("Fatt. Elettronica"),
            );
        }
    }
})