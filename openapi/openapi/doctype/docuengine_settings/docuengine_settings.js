frappe.ui.form.on("Docuengine Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Sincronizza listino da OpenAPI"), () => {
			frappe.call({
				method: "openapi.api.docuengine.pricing.sync_documents",
				freeze: true,
				freeze_message: __("Recupero listino documenti da OpenAPI..."),
				callback: (r) => {
					if (!r.message) return;
					const m = r.message;
					frappe.show_alert({
						message: __(
							"Aggiunti: {0}, Aggiornati: {1}, Disabilitati (non più disponibili): {2}",
							[m.added, m.updated, m.hidden]
						),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		});

		frm.add_custom_button(__("Apri listino completo"), () => {
			frappe.set_route("List", "Docuengine Document Price");
		});

		render_listino_tab(frm);
	},

	default_multiplier(frm) {
		render_listino_tab(frm);
	},
});


function render_listino_tab(frm) {
	const $wrapper = frm.fields_dict.listino_html.$wrapper;
	$wrapper.empty();
	$wrapper.html(`
		<div class="text-muted small mb-2">
			<i class="fa fa-info-circle"></i>
			${__('Listino documenti sincronizzati. Click su una riga per modificare il margine override sul singolo documento.')}
		</div>
		<div id="dc-listino-toolbar" class="d-flex flex-wrap align-items-center mb-2 gap-2"></div>
		<div id="dc-listino-table"></div>
	`);

	const $toolbar = $wrapper.find('#dc-listino-toolbar');
	const $table = $wrapper.find('#dc-listino-table');

	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Docuengine Document Price",
			fields: ["name", "document_name", "category", "cost_eur", "final_price_eur", "multiplier_override", "enabled", "is_sync_service"],
			filters: {},
			order_by: "category asc, document_name asc",
			limit_page_length: 200,
		},
		callback: (r) => {
			const rows = r.message || [];
			if (!rows.length) {
				$table.html(`<div class="text-muted py-4 text-center">${__("Nessun documento sincronizzato. Clicca \"Sincronizza listino da OpenAPI\".")}</div>`);
				return;
			}
			_render_toolbar(frm, $toolbar, rows);
			_render_table($table, rows, frm);
		},
	});
}


function _render_toolbar(frm, $toolbar, rows) {
	const enabled = rows.filter(r => r.enabled).length;
	const totalCost = rows.reduce((s, r) => s + (r.cost_eur || 0), 0);
	const totalFinal = rows.reduce((s, r) => s + (r.final_price_eur || 0), 0);
	const mult = frm.doc.default_multiplier || 1;

	$toolbar.html(`
		<span class="badge bg-light text-dark">${rows.length} ${__("documenti")}</span>
		<span class="badge bg-success-subtle text-success-emphasis">${enabled} ${__("attivi")}</span>
		<span class="text-muted small ms-2">${__("Costo OpenAPI tot")}: € ${totalCost.toFixed(2)}</span>
		<span class="text-muted small">·</span>
		<span class="text-muted small">${__("Moltiplicatore default")}: ×${mult}</span>
		<span class="text-muted small">·</span>
		<span class="text-muted small">${__("Prezzo cliente tot")}: <strong>€ ${totalFinal.toFixed(2)}</strong></span>
		<input id="dc-filter" type="text" class="form-control form-control-sm ms-auto" placeholder="${__("Filtra per nome o categoria...")}" style="max-width: 300px;" />
	`);

	$toolbar.find('#dc-filter').on('input', (e) => {
		const q = e.target.value.toLowerCase();
		document.querySelectorAll('.dc-row').forEach(tr => {
			const txt = (tr.dataset.search || '').toLowerCase();
			tr.style.display = txt.includes(q) ? '' : 'none';
		});
	});
}


function _render_table($table, rows, frm) {
	const grouped = {};
	rows.forEach(r => {
		const cat = r.category || '—';
		if (!grouped[cat]) grouped[cat] = [];
		grouped[cat].push(r);
	});

	let html = `
		<div style="max-height: 600px; overflow-y: auto; border:1px solid var(--border-color); border-radius:6px;">
		<table class="table table-sm small mb-0">
			<thead style="background: var(--gray-50); position: sticky; top: 0; z-index: 1;">
				<tr>
					<th style="width: 40px;"></th>
					<th>${__("Documento")}</th>
					<th>${__("Categoria")}</th>
					<th class="text-end" style="width: 90px;">${__("Costo (€)")}</th>
					<th class="text-end" style="width: 110px;">${__("Moltiplicatore")}</th>
					<th class="text-end" style="width: 110px;">${__("Cliente (€)")}</th>
					<th class="text-end" style="width: 60px;"></th>
				</tr>
			</thead>
			<tbody>
	`;

	const cats = Object.keys(grouped).sort();
	for (const cat of cats) {
		html += `
			<tr style="background: var(--gray-50);">
				<td colspan="7" class="fw-bold py-1">${frappe.utils.escape_html(cat)} <span class="badge bg-light text-dark">${grouped[cat].length}</span></td>
			</tr>
		`;
		for (const r of grouped[cat]) {
			const mult = r.multiplier_override ?? frm.doc.default_multiplier ?? 1;
			const isOverride = r.multiplier_override !== null && r.multiplier_override !== undefined && r.multiplier_override !== '';
			const search = `${r.document_name} ${r.category}`;
			html += `
				<tr class="dc-row" data-search="${frappe.utils.escape_html(search)}" data-name="${frappe.utils.escape_html(r.name)}" style="cursor:pointer;">
					<td>
						${r.enabled
							? `<span title="${__('Attivo')}" class="text-success"><i class="fa fa-check-circle"></i></span>`
							: `<span title="${__('Disabilitato')}" class="text-muted"><i class="fa fa-circle-o"></i></span>`}
					</td>
					<td>
						<div class="fw-semibold">${frappe.utils.escape_html(r.document_name || '')}</div>
						${!r.is_sync_service ? `<small class="text-muted">${__("Async")}</small>` : ''}
					</td>
					<td class="text-muted">${frappe.utils.escape_html(r.category || '—')}</td>
					<td class="text-end font-monospace">${(r.cost_eur || 0).toFixed(2)}</td>
					<td class="text-end font-monospace">
						${isOverride
							? `<span class="badge bg-warning-subtle text-warning-emphasis" title="${__('Override applicato')}">×${mult}</span>`
							: `<span class="text-muted">×${mult}</span>`}
					</td>
					<td class="text-end font-monospace fw-semibold">${(r.final_price_eur || 0).toFixed(2)}</td>
					<td class="text-end">
						<i class="fa fa-pencil text-muted"></i>
					</td>
				</tr>
			`;
		}
	}

	html += `</tbody></table></div>`;
	$table.html(html);

	$table.find('.dc-row').on('click', (e) => {
		const name = e.currentTarget.dataset.name;
		if (name) frappe.set_route("Form", "Docuengine Document Price", name);
	});
}
