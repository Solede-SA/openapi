frappe.ui.form.on("SDI Webhook Log", {
	refresh(frm) {
		if (frm.doc.response_status === "Error") {
			frm.add_custom_button(__("Riprova"), () => {
				frappe.call({
					method: "retry",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("Riesecuzione webhook in corso..."),
					callback(r) {
						if (!r.exc) {
							frappe.show_alert({ message: __("Webhook rieseguito con successo"), indicator: "green" });
							frm.reload_doc();
						}
					},
				});
			});
		}
	},
});
