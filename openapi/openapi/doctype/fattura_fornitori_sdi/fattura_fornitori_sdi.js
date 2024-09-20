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

	},
});