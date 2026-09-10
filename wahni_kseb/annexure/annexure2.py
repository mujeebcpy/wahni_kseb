import datetime
from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from wahni_kseb.annexure.annexure1 import build_name_address


@dataclass
class Annexure2Data:
    """Fields for KSEB Annexure-2; unspecified fields stay empty."""

    name_address_anx2: str
    solar_capacity_anx2: str
    completion_date_anx2: str
    component_details: str = "yes"
    component_specification: str = "Production Meter: yes\nNet Meter : NO"
    images_included: str = "Yes"
    connected_load_anx2: str = ""
    place_anx2: str = ""
    date_anx2: str = ""


def build_annexure2_data(doc) -> Annexure2Data:
    """Build Annexure-2 data from a KSEB Grid Check document."""
    return Annexure2Data(
        name_address_anx2=build_name_address(doc),
        solar_capacity_anx2=f"{doc.proposed_solar_capacity} kW" if doc.proposed_solar_capacity else "",
        completion_date_anx2=datetime.date.today().strftime("%B %Y"),
    )


def fill_annexure2(
    data: Annexure2Data,
    template: str | Path,
    output: str | Path,
) -> None:
    """Fill the KSEB Annexure-2 PDF, including blank fields."""
    writer = PdfWriter()
    writer.append(PdfReader(template))
    for page in writer.pages:
        writer.update_page_form_field_values(page, asdict(data), auto_regenerate=False)
    with open(output, "wb") as fp:
        writer.write(fp)
