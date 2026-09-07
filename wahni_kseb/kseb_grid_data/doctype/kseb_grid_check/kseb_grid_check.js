frappe.ui.form.on("KSEB Grid Check", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Generate Annexure 1"), function () {
            if (!frm.doc.proposed_solar_capacity) {
                frappe.msgprint({
                    title: __("Missing Solar Capacity"),
                    message: __("Please enter Proposed Solar Capacity (kW) before generating Annexure 1."),
                    indicator: "orange"
                });
                return;
            }

            frappe.call({
                method: "wahni_kseb.api.generate_annexure1",
                args: {
                    kseb_grid_check: frm.doc.name
                },
                freeze: true,
                freeze_message: __("Generating Annexure 1..."),
                callback(r) {
                    if (!r.message) {
                        return;
                    }

                    frappe.msgprint({
                        title: __("Annexure 1 Generated"),
                        message: __(
                            'Annexure 1 has been generated successfully. <a href="{0}" target="_blank">Open PDF</a>',
                            [r.message.file_url]
                        ),
                        indicator: "green"
                    });

                    frm.reload_doc();
                }
            });
        });
    }
});