frappe.listview_settings['Sales Invoice'] = {
        formatters: {
        custom_stato_invio: function (value, doc, row) {
                if (value == '') {
                    return '';
                }

                let color = 'black';
                let font_weight = 'normal';

                switch (value) {
                    case 'RC':
                        color = 'green';
                        font_weight = 'bold';
                        break;
                    case 'EC01':
                        color = 'green';
                        font_weight = 'bold';
                        break;
                    case 'NS':
                        color = 'red';
                        font_weight = 'bold';
                        break;
                    case 'MC':
                        color = 'red';
                        font_weight = 'bold';
                        break;
                    case 'EC02':
                        color = 'red';
                        font_weight = 'bold';
                        break;
                }
                
                return `<span style="color:${color}; font-weight: ${font_weight};">${row.custom_stato_invio_descrizione}</span>`;

            }
        },
        
};