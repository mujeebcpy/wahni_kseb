"""Native annexure print formats. No fillable PDF templates are read."""
import base64
from functools import lru_cache
from pathlib import Path

import frappe
from frappe.utils import getdate
from frappe.utils.file_manager import save_file

PRINT_FORMATS = {1: "KSEB Annexure I", 2: "KSEB Annexure II", 3: "KSEB Annexure III"}


@lru_cache(maxsize=1)
def font_css():
    # `src` must not be written as `src:url(...)`: frappe.utils.pdf.get_pdf runs scrub_urls(), which appends
    # " !important" after any `:url(...)`, making the @font-face invalid so wkhtmltopdf renders Malayalam as boxes.
    folder = Path(__file__).resolve().parents[1] / "public" / "fonts" / "manjari"
    return "\n".join(
        "@font-face {font-family: Manjari; font-style:normal; font-weight:" + weight
        + ";src:local('" + local_name + "'), url(data:font/ttf;base64," + base64.b64encode((folder / filename).read_bytes()).decode()
        + ") format('truetype');}"
        for weight, local_name, filename in (("400", "Manjari Regular", "Manjari-Regular.ttf"),
                                             ("700", "Manjari Bold", "Manjari-Bold.ttf"))
    )


def print_context(doc):
    doc.check_permission("read")
    def date_value(key, pattern="%d/%m/%Y"):
        value = doc.get(key)
        return getdate(value).strftime(pattern) if value else ""
    return {
        "font_css": font_css(),
        "name_address": "\n".join(filter(None, [
            ", ".join(str(doc.get(key)) for key in ("consumer_name", "consumer_no", "tariff", "phase") if doc.get(key)),
            doc.get("registered_mobile"), doc.get("customer_email"), doc.get("customer_address")
        ])),
        "capacity": f"{doc.proposed_solar_capacity:g} kW" if doc.proposed_solar_capacity else "",
        **{key: date_value(key) for key in ("completion_date", "date_anx1", "date_anx2", "date_anx3", "acknowledgement_date")},
        "completion_date_anx2": date_value("completion_date_anx2", "%B %Y"),
    }


def generate_annexure(kseb_grid_check, number):
    if not kseb_grid_check:
        frappe.throw("KSEB Grid Check is required.")
    if number not in PRINT_FORMATS:
        frappe.throw("Unsupported annexure number.")
    doc = frappe.get_doc("KSEB Grid Check", kseb_grid_check)
    doc.check_permission("write")
    doc.check_permission("print")
    for field, label in (("consumer_name", "Consumer Name"), ("consumer_no", "Consumer Number"),
                         ("proposed_solar_capacity", "Proposed Solar Capacity (kW)")):
        if not doc.get(field):
            frappe.throw(f"{label} is missing. Complete the Grid Check before generating Annexure {number}.")
    content = frappe.get_print(doc.doctype, doc.name, print_format=PRINT_FORMATS[number], doc=doc, as_pdf=True, no_letterhead=1)
    file = save_file(f"Annexure-{number}-{doc.name}.pdf", content, doc.doctype, doc.name, is_private=1)
    return {"file_url": file.file_url, "file_name": file.file_name,
            "resolved_inputs": {"record": {key: value for key, value in doc.as_dict().items() if key != "annexure_context"}, "values": {key: value for key, value in doc.annexure_context.items() if key != "font_css"}}}
