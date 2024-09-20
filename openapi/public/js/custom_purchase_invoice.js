frappe.ui.form.on('Purchase Invoice', {
    refresh: function (frm) {
        console.log(frm.doc.custom_tipo_di_documento)
        let tipo_documento = frm.doc.custom_tipo_di_documento;
        frappe.db.get_doc("Tipologia di documento e-Invoice", tipo_documento).then(statoDocumento => {
            console.log(statoDocumento);
            if (statoDocumento.tipologia == "AutoFattura") {
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
        }); 
    }
})