frappe.ui.form.on("Lead", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(
            __("Check KSEB Grid Capacity"),
            () => open_kseb_lookup_dialog(frm),
            __("Action")
        );
        frm.add_custom_button(
            __("Install KSEB Bookmarklet"),
            () => open_bookmarklet_install_dialog(),
            __("Action")
        );
    }
});

// The transformer lookup is protected by Cloudflare Turnstile on the KSEB website. The user
// completes the check in a popup and clicks our bookmarklet, which posts the token back here.
const KSEB_VERIFY_URL = "https://wss.kseb.in/selfservices/reCap";
const KSEB_VERIFY_ORIGIN = "https://wss.kseb.in";
const KSEB_MESSAGE_TYPE = "wahni-kseb-turnstile";
const KSEB_BOOKMARKLET_VERSION = 1;
const KSEB_BOOKMARKLET_USED_KEY = "wahni_kseb_bookmarklet_used";

function open_kseb_lookup_dialog(frm) {
    const consumer_no = frm.doc.custom_kseb_consumer_no;
    const mobile = frm.doc.custom_kseb_connected_mobile_no;
    if (!consumer_no) {
        frappe.msgprint(__("Set the KSEB Consumer Number on this Lead first."));
        return;
    }

    const methods = [{ label: __("Without bill details"), value: "without_bill" }];
    if (mobile) {
        methods.unshift({ label: __("Bill lookup"), value: "bill" });
    }

    const dialog = new frappe.ui.Dialog({
        title: __("Check KSEB Grid Capacity"),
        fields: [
            {
                fieldname: "method",
                fieldtype: "Select",
                label: __("Lookup Method"),
                options: methods,
                default: mobile ? "bill" : "without_bill",
                reqd: 1,
                onchange() {
                    dialog.__kseb.step = dialog.get_value("method") === "bill" && !dialog.__kseb.billDone ? "bill" : "verify";
                    update_lookup_dialog(dialog);
                }
            },
            {
                fieldname: "consumer_details",
                fieldtype: "HTML",
                options:
                    `<p><strong>${__("Consumer Number")}:</strong> ${frappe.utils.escape_html(consumer_no)}` +
                    (mobile ? `<br><strong>${__("Registered Mobile")}:</strong> ${frappe.utils.escape_html(mobile)}` : "") +
                    `</p>`
            },
            {
                fieldname: "method_note",
                fieldtype: "HTML"
            },
            {
                fieldname: "bill_captcha_image",
                fieldtype: "HTML"
            },
            {
                fieldname: "bill_captcha_code",
                fieldtype: "Data",
                label: __("Enter Bill CAPTCHA")
            },
            {
                fieldname: "verify_html",
                fieldtype: "HTML"
            },
            {
                fieldname: "turnstile_token",
                fieldtype: "Data",
                label: __("Turnstile Token"),
                description: __("Filled in by the bookmarklet. You can also paste it here.")
            }
        ],
        primary_action_label: __("Continue"),
        primary_action(values) {
            if (dialog.__kseb.step === "bill") {
                run_bill_lookup(frm, dialog, values);
                return;
            }
            fetch_transformer_capacity(frm, dialog, values.turnstile_token);
        }
    });

    dialog.__kseb = {
        step: mobile ? "bill" : "verify",
        billDone: false,
        billSessionId: null,
        busy: false,
        popup: null
    };

    const on_message = (event) => {
        if (event.origin !== KSEB_VERIFY_ORIGIN) return;
        const data = event.data;
        if (!data || data.type !== KSEB_MESSAGE_TYPE || typeof data.token !== "string" || !data.token) return;
        if (data.v !== KSEB_BOOKMARKLET_VERSION) {
            frappe.show_alert({ message: __("A newer KSEB bookmarklet is available. Please reinstall it."), indicator: "orange" });
        }
        dialog.set_value("turnstile_token", data.token);
        fetch_transformer_capacity(frm, dialog, data.token);
    };
    window.addEventListener("message", on_message);
    dialog.onhide = () => {
        window.removeEventListener("message", on_message);
        if (dialog.__kseb.popup && !dialog.__kseb.popup.closed) {
            dialog.__kseb.popup.close();
        }
    };

    dialog.show();
    update_lookup_dialog(dialog);
}

function update_lookup_dialog(dialog) {
    const is_bill_step = dialog.__kseb.step === "bill";
    const without_bill = dialog.get_value("method") === "without_bill";

    dialog.get_field("method_note").$wrapper.html(
        without_bill
            ? `<p class="text-muted">${__("Retrieves section and transformer capacity only. Bill details are not retrieved.")}</p>`
            : `<p class="text-muted">${__("Retrieves bill details first, then the transformer capacity after the KSEB verification.")}</p>`
    );

    dialog.set_df_property("bill_captcha_image", "hidden", !is_bill_step);
    dialog.set_df_property("bill_captcha_code", "hidden", !is_bill_step);
    dialog.set_df_property("bill_captcha_code", "reqd", is_bill_step);
    dialog.set_df_property("verify_html", "hidden", is_bill_step);
    dialog.set_df_property("turnstile_token", "hidden", is_bill_step);
    dialog.get_primary_btn().text(is_bill_step ? __("Fetch Bill Details") : __("Fetch Capacity"));

    if (is_bill_step) {
        if (!dialog.__kseb.billSessionId) {
            load_bill_captcha(dialog);
        }
    } else {
        render_verify_step(dialog);
    }
}

function render_verify_step(dialog, status) {
    const $wrapper = dialog.get_field("verify_html").$wrapper;
    $wrapper.html(`
        ${dialog.__kseb.billDone ? `<p class="text-success">${__("Bill details saved.")}</p>` : ""}
        <ol class="text-muted" style="padding-left: 18px;">
            <li>${__("Click <b>Verify on KSEB</b>. The KSEB page opens in a new window.")}</li>
            <li>${__("Complete the Cloudflare check there. Do not press KSEB's own button.")}</li>
            <li>${__("Click the <b>KSEB → ERPNext</b> bookmarklet. The capacity is fetched automatically.")}</li>
        </ol>
        <p><button type="button" class="btn btn-primary btn-sm kseb-open-verify">${__("Verify on KSEB")}</button></p>
        <p class="kseb-verify-status ${status && status.error ? "text-danger" : "text-muted"}">
            ${frappe.utils.escape_html((status && status.message) || "")}
        </p>
        <div class="kseb-bookmarklet-help"></div>
    `);
    $wrapper.find(".kseb-open-verify").on("click", () => open_kseb_verify_window(dialog));
    render_bookmarklet_help($wrapper.find(".kseb-bookmarklet-help"), bookmarklet_used());
}

function set_verify_status(dialog, message, error = false) {
    dialog.get_field("verify_html").$wrapper.find(".kseb-verify-status")
        .toggleClass("text-danger", error)
        .toggleClass("text-muted", !error)
        .text(message);
}

function open_kseb_verify_window(dialog) {
    dialog.set_value("turnstile_token", "");
    // Must run in the click handler, or the browser blocks the popup. No "noopener":
    // the bookmarklet needs window.opener to send the token back.
    const popup = window.open(KSEB_VERIFY_URL, "kseb_verify", "popup,width=1000,height=850");
    if (!popup) {
        frappe.msgprint(__("The browser blocked the KSEB window. Allow popups for this site and try again."));
        return;
    }
    dialog.__kseb.popup = popup;
    set_verify_status(dialog, __("Waiting for the KSEB verification..."));
}

function run_bill_lookup(frm, dialog, values) {
    if (!dialog.__kseb.billSessionId) {
        frappe.msgprint(__("Please wait for the CAPTCHA to load or refresh it."));
        return;
    }
    frappe.call({
        method: "wahni_kseb.api.fetch_bill_details",
        args: {
            lead: frm.doc.name,
            bill_captcha_code: values.bill_captcha_code,
            bill_session_id: dialog.__kseb.billSessionId
        },
        freeze: true,
        freeze_message: __("Fetching KSEB bill details..."),
        callback(r) {
            if (!r.message) return;
            dialog.__kseb.billDone = true;
            dialog.__kseb.step = "verify";
            update_lookup_dialog(dialog);
        },
        error(xhr) {
            const message = get_frappe_error_message(xhr);
            // A CAPTCHA can be submitted only once, so load a new one after every failure.
            load_bill_captcha(dialog);
            if (is_kseb_validation_error(message) || is_kseb_captcha_error(message)) return;

            frappe.confirm(
                __("Bill lookup failed. Would you like to continue without bill details?"),
                () => dialog.set_value("method", "without_bill")
            );
        }
    });
}

function fetch_transformer_capacity(frm, dialog, token) {
    if (dialog.__kseb.busy) return;
    if (!token) {
        frappe.msgprint(__("Complete the KSEB verification and click the bookmarklet first."));
        return;
    }
    dialog.__kseb.busy = true;
    set_verify_status(dialog, __("Fetching transformer capacity..."));
    frappe.call({
        method: "wahni_kseb.api.fetch_transformer_capacity",
        args: {
            lead: frm.doc.name,
            turnstile_token: token,
            without_bill: dialog.get_value("method") === "without_bill" ? 1 : 0
        },
        freeze: true,
        freeze_message: __("Checking KSEB grid availability..."),
        callback(r) {
            if (!r.message) return;
            mark_bookmarklet_used();
            dialog.hide();
            show_grid_check_result(r.message);
        },
        error(xhr) {
            // A Turnstile token works only once, so the user has to verify again.
            dialog.set_value("turnstile_token", "");
            const message = get_frappe_error_message(xhr);
            set_verify_status(
                dialog,
                is_kseb_turnstile_error(message)
                    ? __("KSEB rejected the verification. Click Verify on KSEB and try again.")
                    : __("Could not fetch the transformer capacity. Click Verify on KSEB to try again."),
                true
            );
        },
        always() {
            dialog.__kseb.busy = false;
        }
    });
}

function load_bill_captcha(dialog) {
    const $wrapper = dialog.get_field("bill_captcha_image").$wrapper;
    const label = __("Bill CAPTCHA");
    dialog.__kseb.billSessionId = null;
    dialog.set_value("bill_captcha_code", "");
    $wrapper.html(
        `<label class="control-label">${label}</label>` +
        `<p class="text-muted">${__("Loading CAPTCHA...")}</p>`
    );
    frappe.call({
        method: "wahni_kseb.api.get_bill_captcha",
        freeze: true,
        freeze_message: __("Loading KSEB CAPTCHA..."),
        callback(r) {
            if (!r.message || !r.message.image || !r.message.session_id) return;
            dialog.__kseb.billSessionId = r.message.session_id;
            $wrapper.html(
                `<label class="control-label">${label}</label><div>` +
                `<img src="${frappe.utils.escape_html(r.message.image)}" alt="${label}" style="width: 360px; max-width: 100%; height: auto; image-rendering: auto;"> ` +
                `<button type="button" class="btn btn-default btn-xs kseb-refresh-captcha">${__("Refresh")}</button></div>`
            );
            $wrapper.find(".kseb-refresh-captcha").on("click", () => load_bill_captcha(dialog));
        }
    });
}

function show_grid_check_result(result) {
    frappe.msgprint({
        title: __("KSEB Grid Check Complete"),
        message: __("Available Capacity: {0} kW", [result.data.balance_available]),
        indicator: "green"
    });
    frappe.set_route("Form", "KSEB Grid Check", result.name);
}

// Bookmarklet

function kseb_bookmarklet_url() {
    // The token is only ever posted to this ERPNext site's origin.
    const target = JSON.stringify(window.location.origin);
    const source =
        `(()=>{` +
        `if(location.origin!=="${KSEB_VERIFY_ORIGIN}"){alert("Open the KSEB DTR Capacity page from ERPNext first.");return;}` +
        `const t=(document.querySelector('[name="cf-turnstile-response"]')||{}).value;` +
        `if(!t){alert("Complete the Cloudflare check on this page first.");return;}` +
        `if(window.opener){window.opener.postMessage({type:"${KSEB_MESSAGE_TYPE}",v:${KSEB_BOOKMARKLET_VERSION},token:t},${target});window.close();return;}` +
        `navigator.clipboard.writeText(t).then(()=>alert("Token copied. Paste it in the Turnstile Token field in ERPNext."),` +
        `()=>prompt("Copy this token and paste it in the Turnstile Token field in ERPNext:",t));` +
        `})();`;
    return "javascript:" + encodeURIComponent(source);
}

function render_bookmarklet_help($container, collapsed) {
    $container.html(`
        <details ${collapsed ? "" : "open"}>
            <summary class="text-muted">${__("First time on this browser? Install the bookmarklet")}</summary>
            <div style="margin-top: 8px;">
                <p class="text-muted">${__("Drag this button to your bookmarks bar. Press Ctrl+Shift+B if the bar is hidden.")}</p>
                <p>
                    <a class="btn btn-default btn-sm kseb-bookmarklet-link">${__("KSEB → ERPNext")}</a>
                    <button type="button" class="btn btn-link btn-sm kseb-copy-bookmarklet">${__("Copy code instead")}</button>
                </p>
                <p class="text-muted small">${__("If dragging does not work, create a new bookmark named \"KSEB → ERPNext\" and paste the copied code as its URL.")}</p>
            </div>
        </details>
    `);
    const url = kseb_bookmarklet_url();
    // Set with attr() so the javascript: URL is not altered by HTML sanitising.
    $container.find(".kseb-bookmarklet-link").attr("href", url).on("click", (event) => {
        event.preventDefault();
        frappe.show_alert(__("Drag this button to your bookmarks bar instead of clicking it."));
    });
    $container.find(".kseb-copy-bookmarklet").on("click", () => frappe.utils.copy_to_clipboard(url));
}

function open_bookmarklet_install_dialog() {
    const dialog = new frappe.ui.Dialog({
        title: __("Install KSEB Bookmarklet"),
        fields: [{ fieldname: "help", fieldtype: "HTML" }]
    });
    const $wrapper = dialog.get_field("help").$wrapper;
    $wrapper.html(`
        <p>${__("The bookmarklet sends the KSEB verification to ERPNext during a grid capacity check. Install it once on each browser.")}</p>
        <div class="kseb-bookmarklet-help"></div>
    `);
    render_bookmarklet_help($wrapper.find(".kseb-bookmarklet-help"), false);
    dialog.show();
}

function bookmarklet_used() {
    try {
        return window.localStorage.getItem(KSEB_BOOKMARKLET_USED_KEY) === "1";
    } catch (e) {
        return false;
    }
}

function mark_bookmarklet_used() {
    try {
        window.localStorage.setItem(KSEB_BOOKMARKLET_USED_KEY, "1");
    } catch (e) {
        // Storage can be blocked; the help box then just stays expanded.
    }
}

// Errors

function get_frappe_error_message(xhr) {
    try {
        const response = JSON.parse(xhr.responseText || "{}");
        return response._server_messages ? JSON.parse(response._server_messages).join(" ") : (response.exception || "");
    } catch (e) {
        return xhr.responseText || "";
    }
}

function is_kseb_captcha_error(message) {
    return /captcha rejected by kseb|captcha is required/i.test(message);
}

function is_kseb_turnstile_error(message) {
    return /turnstile verification/i.test(message);
}

function is_kseb_validation_error(message) {
    return /validation error|on the lead first|invalid consumer number|invalid mobile number/i.test(message);
}
