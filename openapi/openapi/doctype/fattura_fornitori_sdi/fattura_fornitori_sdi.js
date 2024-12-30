// Copyright (c) 2024, Solede SA and contributors
// For license information, please see license.txt

frappe.ui.form.on("Fattura Fornitori SDI", {
    refresh(frm) {
        frm.disable_save();

        frm.add_custom_button(
            __("Scarica PDF"),
            () => {
                let url = "/api/method/openapi.api.sdi.fatture.download?doctype=Fattura Fornitori SDI&docname=" + frm.doc.name + "&type=pdf";
                // window.open(url);
                window.location.href = url
            }
        );

        frm.add_custom_button(
            __("Importa Fattura"),
            () => {
                frappe.call({
                    method: "openapi.api.eInvoice.purchase_invoice.process_supplier_invoice",
                    args: {
                        "json_data_string": frm.doc.dati_fattura,
                        "fattura_fornitori_sdi": frm.doc.name,
                    },
                    callback: function (r) {
                        if (r.message) {
                            frappe.msgprint(r.message);
                            frappe.set_route("Form", "Purchase Invoice", r.message);
                        }
                    },
                    error: function (r) {
                        frappe.throw(r.message);
                    }
                });

            }
        );

	},
});