frappe.ui.form.on('Company', {
    refresh: function (frm) {
        if (frm.doc.custom_business_configuration != null) {
            frm.set_df_property('custom_crea_configurazione_openapi', 'hidden', true);
        }
            

    },
    custom_crea_configurazione_openapi: function (frm) {
        console.log(frm.doc)
        frappe.call({
            type: "POST",
            method: "openapi.api.sdi.configurazione.create_business_register",
            args: {
                data: {
                    "fiscal_id": frm.doc.tax_id,
                    "name": frm.doc.name,
                    "email": frm.doc.tax_id + "@solede.com",
                    "apply_signature": frm.doc.custom_apply_signature,  
                    "apply_legal_storage": frm.doc.custom_apply_legal_storage

                },
            },
            freeze: true,
            callback: function (r) {
                if (r.message) {
                    console.log(r.message)
                    frm.dirty()
                    frm.doc.custom_business_configuration = JSON.stringify(r.message)
                    frm.save()
                    frm.refresh()
                    frappe.msgprint("Configurazione Generata")
                }

            }
        })      
    },
    custom_invia_configurazione: function (frm) {
        frappe.call({
            type: "POST",
            method: "openapi.api.sdi.configurazione.send_configuration",
            args: {
                data: {
                    "name": frm.doc.name,
                }
            },
            freeze: true,
            callback: function (r) {
                if (r.message) {
                    console.log(r.message)
                    frappe.msgprint("Configurazione Inviata")
                }

            }
        })      
    }
})