import base64

import frappe
from frappe.utils import now_datetime
from kseb_client import (
    KSEBCaptchaError,
    KSEBClient,
    KSEBClientError,
    KSEBTurnstileError,
    KSEBValidationError,
)
from wahni_kseb.annexure.printing import generate_annexure

# The Lead dialog looks for this prefix (and the "Turnstile verification" text of
# KSEBTurnstileError) to retry the right step instead of failing.
CAPTCHA_REJECTED = "CAPTCHA rejected by KSEB"

BILL_FIELDS = ("registered_mobile", "consumer_name", "customer_address", "tariff", "phase", "connected_load")


def _captcha_response(captcha, id_field, id_value):
    content_type = captcha.content_type or "image/png"
    return {
        id_field: id_value,
        "image": f"data:{content_type};base64,{base64.b64encode(captcha.image).decode('ascii')}",
    }


def _get_lead_kseb_details(lead, require_mobile):
    """Return the consumer number and mobile saved on the Lead."""
    if not lead:
        frappe.throw("Lead is required")

    lead_doc = frappe.get_doc("Lead", lead)
    lead_doc.check_permission("write")

    consumer_no = (lead_doc.get("custom_kseb_consumer_no") or "").strip()
    mobile = (lead_doc.get("custom_kseb_connected_mobile_no") or "").strip()
    if not consumer_no:
        frappe.throw("Set the KSEB Consumer Number on the Lead first")
    if require_mobile and not mobile:
        frappe.throw("Set the KSEB Connected Mobile Number on the Lead first")
    return consumer_no, mobile


def _call_kseb(what, func):
    """Run a KSEB client call and convert SDK errors into messages for the dialog."""
    try:
        return func()
    except KSEBValidationError as e:
        frappe.throw(str(e))
    except KSEBTurnstileError as e:
        frappe.throw(str(e))
    except KSEBCaptchaError as e:
        frappe.throw(f"{CAPTCHA_REJECTED}: {e}")
    except KSEBClientError as e:
        frappe.throw(f"Unable to retrieve KSEB {what}: {e}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "KSEB Grid Check Error")
        frappe.throw(
            "An unexpected error occurred while checking KSEB data. "
            "Please try again later."
        )


def _get_or_create_check(lead, consumer_no):
    """Return the Lead's KSEB Grid Check, clearing bill details of a different consumer."""
    existing_name = frappe.db.get_value("KSEB Grid Check", {"lead": lead}, "name")
    doc = frappe.get_doc("KSEB Grid Check", existing_name) if existing_name else frappe.new_doc("KSEB Grid Check")

    if doc.consumer_no and doc.consumer_no != consumer_no:
        for field in BILL_FIELDS:
            doc.set(field, None)

    doc.lead = lead
    doc.consumer_no = consumer_no
    if not doc.customer_email:
        doc.customer_email = frappe.db.get_value("Lead", lead, "email_id")
    return doc


def _apply_section(doc, section):
    doc.section = section.section
    doc.section_code = section.office_code
    doc.section_phone = section.phone
    doc.section_email = section.email
    doc.subdivision = section.subdivision
    doc.subdivision_email = section.subdivision_email
    doc.division = section.division
    doc.division_phone = section.division_phone
    doc.division_email = section.division_email


def _apply_bill(doc, mobile, bill):
    doc.registered_mobile = mobile
    doc.consumer_name = bill.consumer_name
    doc.customer_address = bill.customer_address
    doc.tariff = bill.tariff
    doc.phase = (bill.phase or "").split(" ")[0]
    doc.connected_load = bill.connected_load


def _apply_transformer(doc, transformer):
    doc.transformer_name = transformer.transformer_name
    doc.transformer_capacity_kva = transformer.capacity_kva
    doc.allowed_cap = transformer.allowed_cap
    doc.regi = transformer.regi
    doc.comp_cap = transformer.comp_cap
    doc.balance_available = transformer.balance_available
    doc.grid_availability = "Available" if (doc.balance_available or 0) > 0 else "Not Available"
    doc.kseb_as_on = transformer.as_on
    doc.last_checked = now_datetime()


def _save(doc):
    if doc.is_new():
        doc.insert()
    else:
        doc.save()
    return {"name": doc.name, "data": doc.as_dict()}


@frappe.whitelist()
def get_bill_captcha():
    """Return a bill download CAPTCHA for the bill lookup flow."""
    try:
        captcha = KSEBClient().get_bill_captcha()
        return _captcha_response(captcha, "session_id", captcha.session_id)
    except KSEBClientError as e:
        frappe.throw(f"Unable to retrieve KSEB bill CAPTCHA: {e}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "KSEB CAPTCHA Error")
        frappe.throw("Unable to retrieve the KSEB bill CAPTCHA. Please try again later.")


@frappe.whitelist()
def fetch_bill_details(lead, bill_captcha_code, bill_session_id):
    """Step 1 of the bill lookup: save section and bill details for the Lead's consumer.

    The bill CAPTCHA can be used only once, so the details are saved before the
    Turnstile step and are kept if that step fails.
    """
    consumer_no, mobile = _get_lead_kseb_details(lead, require_mobile=True)
    if not bill_captcha_code or not bill_session_id:
        frappe.throw("Bill CAPTCHA is required. Please load a new CAPTCHA.")

    def fetch():
        client = KSEBClient()
        section = client.get_section(consumer_no)
        pdf_bytes = client.download_bill(
            consumer_no, mobile, captcha_code=bill_captcha_code, session_id=bill_session_id
        )
        return section, client.parse_bill(pdf_bytes, consumer_no)

    section, bill = _call_kseb("bill details", fetch)

    doc = _get_or_create_check(lead, consumer_no)
    doc.lookup_method = "Bill"
    _apply_section(doc, section)
    _apply_bill(doc, mobile, bill)
    return _save(doc)


@frappe.whitelist()
def fetch_transformer_capacity(lead, turnstile_token, without_bill=0):
    """Fetch and save the transformer capacity for the Lead's consumer.

    ``turnstile_token`` comes from the Cloudflare Turnstile check the user completed on
    the KSEB website. Section details are fetched here when the bill step was skipped.
    """
    consumer_no, _ = _get_lead_kseb_details(lead, require_mobile=False)
    without_bill = frappe.utils.cint(without_bill)
    doc = _get_or_create_check(lead, consumer_no)
    fetch_section = without_bill or not doc.section_code

    def fetch():
        client = KSEBClient()
        section = client.get_section(consumer_no) if fetch_section else None
        transformer = client.get_transformer(consumer_no, turnstile_token=turnstile_token or "")
        return section, transformer

    section, transformer = _call_kseb("transformer capacity", fetch)

    if without_bill:
        doc.lookup_method = "Without Bill"
    if section:
        _apply_section(doc, section)
    _apply_transformer(doc, transformer)
    return _save(doc)


@frappe.whitelist()
def generate_annexure1(kseb_grid_check):
    return generate_annexure(kseb_grid_check, 1)


@frappe.whitelist()
def generate_annexure2(kseb_grid_check):
    return generate_annexure(kseb_grid_check, 2)


@frappe.whitelist()
def generate_annexure3(kseb_grid_check):
    return generate_annexure(kseb_grid_check, 3)
