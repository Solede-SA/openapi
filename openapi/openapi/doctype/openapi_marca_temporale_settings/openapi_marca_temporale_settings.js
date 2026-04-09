// Copyright (c) 2026, Solede SA and contributors
// For license information, please see license.txt

frappe.ui.form.on("OpenApi Marca Temporale Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Controlla Saldo"), () => {
			frm.call("check_lotto").then((r) => {
				if (r.message) {
					frappe.msgprint(
						`Disponibili: <strong>${r.message.available}</strong><br>` +
						`Usate: <strong>${r.message.used}</strong>`
					);
					frm.reload_doc();
				}
			});
		});

		frm.add_custom_button(__("Acquista Lotto"), () => {
			frappe.confirm(
				`Acquistare un lotto di <strong>${frm.doc.qty_acquisto || 100}</strong> marche ` +
				`<strong>${frm.doc.provider || "infocert"}</strong>?<br><br>` +
				`L'importo verrà addebitato sul portafoglio OpenAPI.it.`,
				() => {
					frm.call("acquista_lotto").then((r) => {
						if (r.message) {
							frappe.msgprint(
								`Lotto acquistato: <strong>${r.message.qty}</strong> marche`
							);
							frm.reload_doc();
						}
					});
				}
			);
		});

		frm.add_custom_button(__("Lista Lotti"), () => {
			frm.call("get_lotti").then((r) => {
				if (r.message && r.message.length) {
					let rows = r.message.map((l) =>
						`<tr>
							<td style="padding:6px;border-bottom:1px solid #ddd">${l.type || ""}</td>
							<td style="padding:6px;border-bottom:1px solid #ddd">${l.qty_marca || ""}</td>
							<td style="padding:6px;border-bottom:1px solid #ddd">${l.username || ""}</td>
							<td style="padding:6px;border-bottom:1px solid #ddd">${l.password || ""}</td>
							<td style="padding:6px;border-bottom:1px solid #ddd">${l.timestamp_acquisto || ""}</td>
						</tr>`
					).join("");
					frappe.msgprint(
						`<table style="width:100%;border-collapse:collapse">
							<thead><tr>
								<th style="padding:6px;border-bottom:2px solid #333">Tipo</th>
								<th style="padding:6px;border-bottom:2px solid #333">Qty</th>
								<th style="padding:6px;border-bottom:2px solid #333">Username</th>
								<th style="padding:6px;border-bottom:2px solid #333">Password</th>
								<th style="padding:6px;border-bottom:2px solid #333">Acquisto</th>
							</tr></thead>
							<tbody>${rows}</tbody>
						</table>`,
						__("Lotti Acquistati")
					);
				} else {
					frappe.msgprint(__("Nessun lotto trovato"));
				}
			});
		});
	},
});
