import frappe
from pathlib import Path
from frappe.utils import now_datetime
from kseb_client import KSEBClient, KSEBValidationError, KSEBClientError
from wahni_kseb.annexure.annexure1 import (
    build_annexure1_data,
    fill_annexure1,
)

@frappe.whitelist()
def check_grid_capacity(lead, consumer_no, registered_mobile):
    if not lead:
        frappe.throw("Lead is required")

    if not consumer_no:
        frappe.throw("Consumer Number is required")

    if not registered_mobile:
        frappe.throw("Registered Mobile is required")

    try:
        client = KSEBClient()

        result = client.get_grid_capacity(
            consumer_no=consumer_no,
            mobile=registered_mobile,
        )

    except KSEBValidationError as e:
        frappe.throw(str(e))

    except KSEBClientError as e:
        frappe.throw(
            f"Unable to retrieve KSEB information: {e}"
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "KSEB Grid Check Error",
        )

        frappe.throw(
            "An unexpected error occurred while checking KSEB data. "
            "Please try again later."
        )
    last_checked = now_datetime()
    existing_name = frappe.db.get_value(
    "KSEB Grid Check",
    {"lead": lead},
    "name",
)

    if existing_name:
        doc = frappe.get_doc("KSEB Grid Check", existing_name)
    else:
        doc = frappe.new_doc("KSEB Grid Check")
        doc.lead = lead

    if result.transformer.balance_available > 0:
        grid_availability = "Available"
    else:
        grid_availability = "Not Available"

    # KSEB input
    doc.consumer_no = consumer_no
    doc.registered_mobile = registered_mobile

    # KSEB Consumer
    doc.consumer_name = result.bill.consumer_name
    doc.customer_address = result.bill.customer_address
    doc.tariff = result.bill.tariff
    doc.phase = result.bill.phase
    doc.connected_load = result.bill.connected_load

    # KSEB Section
    doc.section = result.section.section
    doc.section_code = result.section.office_code
    doc.section_phone = result.section.phone
    doc.section_email = result.section.email
    doc.subdivision = result.section.subdivision
    doc.subdivision_email = result.section.subdivision_email
    doc.division = result.section.division
    doc.division_phone = result.section.division_phone
    doc.division_email = result.section.division_email

    # Transformer / Grid
    doc.transformer_name = result.transformer.transformer_name
    doc.allowed_cap = result.transformer.allowed_cap
    doc.regi = result.transformer.regi
    doc.comp_cap = result.transformer.comp_cap
    doc.balance_available = result.transformer.balance_available

    # Result
    doc.grid_availability = grid_availability
    doc.last_checked = last_checked

    # Save
    if doc.is_new():
        doc.insert()
    else:
        doc.save()

    return {
        "name": doc.name,
        "data": doc.as_dict(),
    }


@frappe.whitelist()
def generate_annexure1(kseb_grid_check):
    """Generate Annexure-1 PDF for a KSEB Grid Check."""

    if not kseb_grid_check:
        frappe.throw("KSEB Grid Check is required.")

    doc = frappe.get_doc("KSEB Grid Check", kseb_grid_check)

    if not doc.consumer_name:
        frappe.throw("Consumer Name is missing.")

    if not doc.consumer_no:
        frappe.throw("Consumer Number is missing.")

    if not doc.proposed_solar_capacity:
        frappe.throw(
            "Please enter Proposed Solar Capacity (kW) before generating Annexure 1."
        )

    # Build data for the PDF
    data = build_annexure1_data(doc)

    # Locate PDF template inside the app
    template = (
        Path(frappe.get_app_path("wahni_kseb"))
        / "templates"
        / "kseb-Annexure-1.pdf"
    )

    if not template.exists():
        frappe.throw("Annexure 1 PDF template not found.")

    # Temporary output location
    output_dir = Path(frappe.get_site_path("private", "files"))
    output_dir.mkdir(parents=True, exist_ok=True)

    output = output_dir / f"Annexure-1-{doc.name}.pdf"

    fill_annexure1(
        data=data,
        template=template,
        output=output
    )
    file_doc = frappe.get_doc(
    {
        "doctype": "File",
        "file_name": output.name,
        "file_url": f"/private/files/{output.name}",
        "attached_to_doctype": "KSEB Grid Check",
        "attached_to_name": doc.name,
        "is_private": 1,
    }
)

    file_doc.insert(ignore_permissions=True)

    return {
        "file_url": file_doc.file_url,
        "file_name": file_doc.file_name,
    }
