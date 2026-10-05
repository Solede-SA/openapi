// Finestre della verifica creditizia OpenAPI, condivise da Customer e DAE Order (daeok)
frappe.provide("openapi.credit_check");

(() => {
	const GREY = "#6c757d";
	const RATING_COLORS = {
		A1: "#28a745", A2: "#5cb85c", A3: "#8bc34a",
		B1: "#ffc107", B2: "#ff9800", B3: "#ff5722",
		C1: "#f44336", C2: "#d32f2f", C3: "#b71c1c",
	};
	// Valori di risk_score restituiti da OpenAPI Credit Scoring
	const RISK_COLORS = {
		"VERDE SCURO": "#1e7e34", VERDE: "#28a745", "VERDE CHIARO": "#8bc34a",
		GIALLO: "#ffc107", GRIGIO: GREY,
		ROSSO: "#f44336", "ROSSO VIVO": "#d32f2f", "ROSSO SCURO": "#b71c1c",
	};
	const ALERT_CLASSES = { A: "success", B: "warning", C: "danger" };
	const OUTCOMES = {
		approved: ["Approvato", "#28a745"],
		rejected: ["Rifiutato", "#dc3545"],
		pending: ["In revisione", "#ffc107"],
	};

	const text = (value) => frappe.utils.escape_html(value === null || value === undefined || value === "" ? "N/D" : String(value));
	const euro = (value) => (value ? format_currency(value, "EUR") : "N/D");
	const badge = (label, color, size) =>
		`<span class="badge" style="font-size: ${size}; background-color: ${color}; color: white; padding: 10px 20px;">${text(label)}</span>`;

	function table(title, headers, rows) {
		if (!rows.length) return "";
		return `<h5 class="mt-4">${title}</h5>
			<table class="table table-sm table-striped">
				<thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
				<tbody>${rows.map((cells) => `<tr>${cells.map((c) => `<td>${text(c)}</td>`).join("")}</tr>`).join("")}</tbody>
			</table>`;
	}

	function show(title, html, width, actions) {
		const dialog = new frappe.ui.Dialog({
			title,
			fields: [{ fieldtype: "HTML", fieldname: "credit_check_html", options: html }],
			primary_action_label: __("Chiudi"),
			primary_action() { this.hide(); },
			...actions,
		});
		dialog.show();
		dialog.$wrapper.find(".modal-dialog").css("max-width", width);
	}

	// data: risposta di Credit Scoring Advanced; opts.outcome: esito del DAE Order; opts.on_save: azione «Salva nel Cliente»
	openapi.credit_check.show_score = function (data, { title = __("Verifica Creditizia"), outcome, on_save } = {}) {
		const outcome_html = outcome
			? `<div class="text-center mb-4">${badge(OUTCOMES[outcome][0], OUTCOMES[outcome][1], "1.2em")}</div>`
			: "";
		const html = `
			${outcome_html}
			<div class="row mb-4">
				<div class="col-md-6 text-center"><h5>Rating</h5>${badge(data.rating, RATING_COLORS[data.rating] || GREY, "2em")}</div>
				<div class="col-md-6 text-center"><h5>Risk Score</h5>${badge(data.risk_score, RISK_COLORS[data.risk_score] || GREY, "1.5em")}</div>
			</div>
			<div class="alert alert-${ALERT_CLASSES[(data.rating || "")[0]] || "secondary"}">
				<strong>Descrizione Rischio:</strong> ${text(data.risk_score_description)}
			</div>
			<table class="table table-bordered"><tbody>
				<tr><th style="width: 40%;">Limite di Credito Operativo</th><td><strong>${text(euro(data.operational_credit_limit))}</strong></td></tr>
				<tr><th>Indice di Rischio (1-990)</th><td>${text(data.risk_severity)}</td></tr>
				<tr><th>Ragione Sociale</th><td>${text(data.organization_name)}</td></tr>
				<tr><th>Partita IVA</th><td>${text(data.vat)}</td></tr>
				<tr><th>Codice Fiscale</th><td>${text(data.tax)}</td></tr>
			</tbody></table>
			<p class="text-muted small">Dati aggiornati al: ${text(data.requested_at)}</p>`;
		const actions = on_save
			? {
				primary_action_label: __("Salva nel Cliente"),
				primary_action() { on_save(); this.hide(); },
				secondary_action_label: __("Chiudi"),
			}
			: {};
		show(title, html, "600px", actions);
	};

	// data: dettaglio di OpenAPI IT-negativita/{id}/dettaglio
	openapi.credit_check.show_negativita = function (data, title) {
		const protesti = data.protesti || [];
		const pregiudizievoli = data.pregiudizievoli || [];
		const procedure = data.procedure || [];
		const total = protesti.length + pregiudizievoli.length + procedure.length;

		const html = `
			<div class="text-center mb-4">
				${badge(total ? `Trovate ${total} negatività` : "Nessuna negatività", total ? "#dc3545" : "#28a745", "1.5em")}
			</div>
			<table class="table table-bordered"><tbody>
				<tr><th style="width: 50%;">Protesti</th><td><strong>${protesti.length}</strong></td></tr>
				<tr><th>Pregiudizievoli</th><td><strong>${pregiudizievoli.length}</strong></td></tr>
				<tr><th>Procedure Concorsuali</th><td><strong>${procedure.length}</strong></td></tr>
			</tbody></table>
			${table(
				"Protesti",
				["Soggetto", "Data levata", "Tipo", "Importo", "Comune", "Motivo mancato pagamento"],
				protesti.flatMap((p) => (p.effetti || []).map((e) =>
					[p.denominazione, e.data_levata, e.tipo_effetto, euro(e.importo), e.comune_levata, e.motivo_rifiuto_pagamento])),
			)}
			${table(
				"Pregiudizievoli",
				["Data", "Tipo", "Importo iscritto", "Conservatoria", "Cancellata", "Sunto"],
				pregiudizievoli.map((p) => [
					p.data_registrazione, p.pregiudizievole, euro(p.importo_iscritto), p.conservatoria,
					p.cancellata ? "Sì" : "No", p.sunto_pregiudizievole,
				]),
			)}
			${table(
				"Procedure Concorsuali",
				["Data provvedimento", "Procedura", "Tribunale", "Chiusura"],
				procedure.map((p) => [p.data_provvedimento, p.descrizione_procedura, p.tribunale, p.data_chiusura]),
			)}`;
		show(title, html, "900px");
	};
})();
