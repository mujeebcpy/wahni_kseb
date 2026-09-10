from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from wahni_kseb.annexure.annexure1 import build_name_address


@dataclass
class Annexure3Data:
    """Fields for KSEB Annexure-3; unspecified fields stay empty."""

    name_address_anx3: str
    solar_capacity_anx3: str
    specification_anx3: str = "yes"
    solar_regno: str = ""
    inspection_certificate: str = ""
    place_anx3: str = ""
    date_anx3: str = ""


def build_annexure3_data(doc) -> Annexure3Data:
    """Build Annexure-3 data from a KSEB Grid Check document."""
    return Annexure3Data(
        name_address_anx3=build_name_address(doc),
        solar_capacity_anx3=f"{doc.proposed_solar_capacity} kW" if doc.proposed_solar_capacity else "",
    )


def fill_annexure3(
    data: Annexure3Data,
    template: str | Path,
    output: str | Path,
) -> None:
    """Fill the KSEB Annexure-3 PDF, including blank fields."""
    writer = PdfWriter()
    writer.append(PdfReader(template))
    for page in writer.pages:
        writer.update_page_form_field_values(page, asdict(data), auto_regenerate=False)
    with open(output, "wb") as fp:
        writer.write(fp)
