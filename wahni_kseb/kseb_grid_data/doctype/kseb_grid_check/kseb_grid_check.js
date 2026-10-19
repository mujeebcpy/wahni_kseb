frappe.ui.form.on("KSEB Grid Check", {
    onload(frm) {
        if (!frm.is_new()) {
            return;
        }

        const month_year = moment().locale("en").format("MMMM YYYY");
        ["completion_date", "completion_date_anx2"].forEach((field) => {
            if (!frm.doc[field]) {
                frm.set_value(field, month_year);
            }
        });
    },

    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        [1, 2, 3].forEach((annexure_number) => {
            frm.add_custom_button(__("Annexure {0}", [annexure_number]), async function () {
                if (!frm.doc.proposed_solar_capacity) {
                    frappe.msgprint({
                        title: __("Missing Solar Capacity"),
                        message: __("Please enter Proposed Solar Capacity (kW) before generating Annexure {0}.", [annexure_number]),
                        indicator: "orange"
                    });
                    return;
                }

                if (frm.is_dirty()) {
                    await frm.save();
                }

                frappe.call({
                    method: `wahni_kseb.api.generate_annexure${annexure_number}`,
                    args: {
                        kseb_grid_check: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __("Generating Annexure {0}...", [annexure_number]),
                    callback(r) {
                        if (!r.message) {
                            return;
                        }

                        frappe.msgprint({
                            title: __("Annexure {0} Generated", [annexure_number]),
                            message: __(
                                'Annexure {0} has been generated successfully. <a href="{1}" target="_blank">Open PDF</a>',
                                [annexure_number, r.message.file_url]
                            ),
                            indicator: "green"
                        });

                        frm.reload_doc();
                    }
                });
            }, __("Generate"));
        });
    }
});
