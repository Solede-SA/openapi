// Pulsante per rileggere dal fornitore lo stato dei mittenti.
//
// Sta qui e non in una schermata degli studi perché l'alias è di piattaforma: uno studio non può
// farci nulla, e finché non è APPROVED non parte un SMS per nessuno.
frappe.ui.form.on("OpenApi SMS Settings", {
	refresh(frm) {
		const chiama = (method, freeze_message) =>
			frm.call({ doc: frm.doc, method, freeze: true, freeze_message, callback: () => frm.reload_doc() });

		frm.add_custom_button(__("Aggiorna stato mittenti"), () =>
			chiama("refresh_senders", __("Lettura in corso…")),
		);
		frm.add_custom_button(__("Registra il mittente"), () =>
			chiama("register_sender", __("Registrazione in corso…")),
		);
	},
});
