from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from bike24.errors import ReturnFormError
from bike24.models import Address, OrderDetails, OrderItem, PersonalDetails
from bike24.returns import build_return_form_data, write_return_form


def profile(*, with_invoice_address: bool = True) -> PersonalDetails:
    return PersonalDetails(
        email="person@example.com",
        invoice_address=(
            Address(first_name="Test", last_name="Person")
            if with_invoice_address
            else None
        ),
        delivery_addresses=(
            Address(
                first_name="Delivery",
                last_name="Person",
                is_default=True,
            ),
        ),
    )


def order(item_count: int = 2) -> OrderDetails:
    items = tuple(
        OrderItem(
            title=f"Example Product {index}",
            item_number=f"ITEM{index}",
            options={"Size": str(index)},
            shipped_quantity=index,
        )
        for index in range(1, item_count + 1)
    )
    return OrderDetails(
        number="123456789",
        date="2026-01-01",
        status="Shipped",
        items=items,
    )


def test_build_return_form_data_uses_profile_and_selected_order_items() -> None:
    data = build_return_form_data(
        profile(),
        order(),
        item_numbers=["ITEM2"],
    )

    assert data.name == "Test Person"
    assert data.email == "person@example.com"
    assert data.order_number == "123456789"
    assert len(data.lines) == 1
    assert data.lines[0].item_number == "ITEM2"
    assert data.lines[0].quantity == 2
    assert data.lines[0].description == "Example Product 2 (Size: 2)"


def test_build_return_form_data_uses_default_delivery_name() -> None:
    data = build_return_form_data(profile(with_invoice_address=False), order())

    assert data.name == "Delivery Person"


@pytest.mark.parametrize(
    ("item_numbers", "match"),
    [
        ([], "Select at least one"),
        (["UNKNOWN"], "not found"),
        (["ITEM1", "ITEM1"], "only once"),
    ],
)
def test_build_return_form_data_rejects_invalid_selection(
    item_numbers: list[str],
    match: str,
) -> None:
    with pytest.raises(ReturnFormError, match=match):
        build_return_form_data(profile(), order(), item_numbers=item_numbers)


def test_build_return_form_data_requires_selection_for_large_order() -> None:
    with pytest.raises(ReturnFormError, match="4 return rows"):
        build_return_form_data(profile(), order(item_count=5))


def test_write_return_form_creates_valid_editable_pdf(tmp_path: Path) -> None:
    data = build_return_form_data(profile(), order())
    output = write_return_form(data, tmp_path / "return.pdf")

    reader = PdfReader(output)
    fields = reader.get_fields() or {}
    assert len(reader.pages) == 2
    assert len(fields) == 21
    assert fields["name"]["/V"] == "Test Person"
    assert fields["email"]["/V"] == "person@example.com"
    assert fields["order_number"]["/V"] == "123456789"
    assert fields["is_return"]["/V"] == "/Yes"
    assert fields["return_item_1"]["/V"] == "ITEM1"
    assert fields["return_qty_1"]["/V"] == "1"
    assert fields["return_brand_1"]["/V"] == "Example Product 1 (Size: 1)"
    assert fields["return_item_2"]["/V"] == "ITEM2"
    assert output.stat().st_mode & 0o777 == 0o600

    widgets = []
    for page in reader.pages:
        for reference in page.get("/Annots", []):
            annotation = reference.get_object()
            if annotation.get("/Subtype") == "/Widget":
                widgets.append(annotation)
    assert len(widgets) == 21
    assert all(widget.get("/AP", {}).get("/N") for widget in widgets)


def test_write_return_form_does_not_overwrite_without_permission(
    tmp_path: Path,
) -> None:
    output = tmp_path / "return.pdf"
    output.write_bytes(b"existing")

    with pytest.raises(ReturnFormError, match="already exists"):
        write_return_form(build_return_form_data(profile(), order()), output)
