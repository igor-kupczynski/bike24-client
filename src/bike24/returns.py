"""Create editable BIKE24 return forms from account data."""

from __future__ import annotations

import os
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.resources import files
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject
from reportlab.lib.colors import Color, black, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from .errors import ReturnFormError
from .models import Address, OrderDetails, OrderItem, PersonalDetails

PAGE_WIDTH = 595.276
PAGE_HEIGHT = 419.528
MAX_RETURN_LINES = 4
TEMPLATE_NAME = "assets/BIKE24_Return_form.pdf"


@dataclass(frozen=True, slots=True)
class ReturnFormLine:
    item_number: str
    quantity: int
    description: str


@dataclass(frozen=True, slots=True)
class ReturnFormData:
    name: str
    email: str
    order_number: str
    lines: tuple[ReturnFormLine, ...]


def _full_name(address: Address | None) -> str:
    if address is None:
        return ""
    return " ".join(
        part.strip()
        for part in (address.first_name, address.last_name)
        if part and part.strip()
    )


def _account_name(profile: PersonalDetails) -> str:
    name = _full_name(profile.invoice_address)
    if name:
        return name
    default = next(
        (address for address in profile.delivery_addresses if address.is_default),
        None,
    )
    return _full_name(default or next(iter(profile.delivery_addresses), None))


def _item_description(item: OrderItem) -> str:
    options = ", ".join(f"{label}: {value}" for label, value in item.options.items())
    return f"{item.title} ({options})" if options else item.title


def build_return_form_data(
    profile: PersonalDetails,
    order: OrderDetails,
    *,
    item_numbers: Sequence[str] | None = None,
) -> ReturnFormData:
    """Select order items and map account data onto the return form."""

    name = _account_name(profile)
    if not name:
        raise ReturnFormError("The BIKE24 profile has no customer name")

    available: dict[str, OrderItem] = {}
    for item in order.items:
        if not item.item_number:
            raise ReturnFormError(f"Order item {item.title!r} has no item number")
        if item.item_number in available:
            raise ReturnFormError(
                f"Order {order.number} contains duplicate item number {item.item_number}"
            )
        available[item.item_number] = item

    if item_numbers is None:
        selected = list(order.items)
    else:
        requested = list(item_numbers)
        if len(requested) != len(set(requested)):
            raise ReturnFormError("Each --item may be selected only once")
        unknown = [number for number in requested if number not in available]
        if unknown:
            raise ReturnFormError(
                f"Item(s) not found in order {order.number}: {', '.join(unknown)}"
            )
        selected = [available[number] for number in requested]

    if not selected:
        raise ReturnFormError("Select at least one item for the return form")
    if len(selected) > MAX_RETURN_LINES:
        raise ReturnFormError(
            f"The form has {MAX_RETURN_LINES} return rows; select items with --item"
        )

    lines_list: list[ReturnFormLine] = []
    for item in selected:
        if item.shipped_quantity is None or item.shipped_quantity < 1:
            raise ReturnFormError(
                f"Order item {item.item_number!r} has no returnable quantity"
            )
        lines_list.append(
            ReturnFormLine(
                item_number=item.item_number or "",
                quantity=item.shipped_quantity,
                description=_item_description(item),
            )
        )
    return ReturnFormData(
        name=name,
        email=profile.email,
        order_number=order.number,
        lines=tuple(lines_list),
    )


def _ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _font_size(value: str, width: float, preferred: float) -> float:
    value = _ascii(value)
    size = preferred
    while size > 6 and pdfmetrics.stringWidth(value, "Helvetica", size) > width - 4:
        size -= 0.5
    return size


def _text_field(
    form: Any,
    *,
    name: str,
    value: str,
    x: float,
    y: float,
    width: float,
    height: float = 13,
    font_size: float = 9,
) -> None:
    safe_value = _ascii(value)
    form.textfield(
        name=name,
        tooltip=name,
        x=x,
        y=y,
        width=width,
        height=height,
        borderWidth=0.4,
        borderColor=Color(0.55, 0.55, 0.55),
        fillColor=Color(1, 1, 0.92),
        textColor=black,
        fontName="Helvetica",
        fontSize=_font_size(safe_value, width, font_size),
        forceBorder=True,
        value=safe_value,
    )


def _checkbox(
    form: Any,
    *,
    name: str,
    x: float,
    y: float,
    checked: bool,
) -> None:
    form.checkbox(
        name=name,
        tooltip=name,
        x=x,
        y=y,
        size=12,
        buttonStyle="check",
        borderWidth=0.6,
        borderColor=black,
        fillColor=white,
        checked=checked,
    )


def _overlay(data: ReturnFormData) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    pdf.setFillColor(Color(1, 1, 1, alpha=0))
    pdf.rect(0, 0, 1, 1, fill=0, stroke=0)
    form = pdf.acroForm

    _text_field(
        form,
        name="name",
        value=data.name,
        x=120,
        y=PAGE_HEIGHT - 94,
        width=190,
        height=14,
        font_size=10,
    )
    _text_field(
        form,
        name="email",
        value=data.email,
        x=360,
        y=PAGE_HEIGHT - 94,
        width=205,
        height=14,
    )
    _text_field(
        form,
        name="order_number",
        value=data.order_number,
        x=98,
        y=PAGE_HEIGHT - 118,
        width=200,
        height=14,
        font_size=10,
    )
    _checkbox(
        form,
        name="is_return",
        x=29.35,
        y=PAGE_HEIGHT - 156,
        checked=True,
    )
    _checkbox(
        form,
        name="is_warranty",
        x=29.35,
        y=PAGE_HEIGHT - 282,
        checked=False,
    )

    return_y = (192.25, 210.25, 228.25, 246.25)
    for index, row_top in enumerate(return_y, start=1):
        line = data.lines[index - 1] if index <= len(data.lines) else None
        y = PAGE_HEIGHT - row_top
        _text_field(
            form,
            name=f"return_item_{index}",
            value=line.item_number if line else "",
            x=28.35,
            y=y,
            width=98,
        )
        _text_field(
            form,
            name=f"return_qty_{index}",
            value=str(line.quantity) if line else "",
            x=136.06,
            y=y,
            width=98,
        )
        _text_field(
            form,
            name=f"return_brand_{index}",
            value=line.description if line else "",
            x=243.78,
            y=y,
            width=320,
            font_size=8,
        )

    warranty_y = PAGE_HEIGHT - 318.25
    _text_field(
        form,
        name="warranty_item_1",
        value="",
        x=28.35,
        y=warranty_y,
        width=98,
    )
    _text_field(
        form,
        name="warranty_qty_1",
        value="",
        x=136.06,
        y=warranty_y,
        width=98,
    )
    _text_field(
        form,
        name="warranty_brand_1",
        value="",
        x=243.78,
        y=warranty_y,
        width=320,
    )
    _text_field(
        form,
        name="damage",
        value="",
        x=28.35,
        y=PAGE_HEIGHT - 360.25,
        width=538,
    )

    pdf.save()
    return buffer.getvalue()


def write_return_form(
    data: ReturnFormData,
    output_path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
) -> Path:
    """Write an editable, prefilled copy of the official BIKE24 return form."""

    output = Path(output_path).expanduser().resolve()
    if output.exists() and not overwrite:
        raise ReturnFormError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    template_bytes = files("bike24").joinpath(TEMPLATE_NAME).read_bytes()
    template = PdfReader(BytesIO(template_bytes))
    overlay = PdfReader(BytesIO(_overlay(data)))
    writer = PdfWriter()
    writer.clone_document_from_reader(template)
    writer.pages[0].merge_page(overlay.pages[0])

    acro_form = overlay.trailer["/Root"]["/AcroForm"].get_object().clone(writer)
    acro_form[NameObject("/NeedAppearances")] = BooleanObject(False)
    writer.root_object[NameObject("/AcroForm")] = acro_form

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if not overwrite:
        flags |= os.O_EXCL
    try:
        descriptor = os.open(output, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            writer.write(stream)
        output.chmod(0o600)
    except OSError as exc:
        raise ReturnFormError(f"Could not write return form: {exc}") from exc
    return output
