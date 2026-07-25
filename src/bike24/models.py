"""Data returned by the BIKE24 client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Address:
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    street: str | None = None
    house_number: str | None = None
    addition: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: int | None = None
    country_state: int | None = None
    phone: str | None = None
    id: str | None = None
    is_default: bool = False

    @classmethod
    def from_api(cls, value: dict[str, Any] | None) -> Address | None:
        if not value:
            return None
        return cls(
            first_name=value.get("firstName"),
            last_name=value.get("lastName"),
            company=value.get("company"),
            street=value.get("street"),
            house_number=value.get("houseNumber"),
            addition=value.get("addition"),
            postal_code=value.get("postalCode"),
            city=value.get("city"),
            country=value.get("country"),
            country_state=value.get("countryState"),
            phone=value.get("phone"),
            id=value.get("id"),
            is_default=bool(value.get("isDefault", False)),
        )


@dataclass(frozen=True, slots=True)
class PersonalDetails:
    email: str
    phone: str | None = None
    account_type: str | None = None
    invoice_address: Address | None = None
    delivery_addresses: tuple[Address, ...] = ()
    default_payment: int | None = None
    vat_number: str | None = None
    vat_status: str | None = None

    @classmethod
    def from_api(cls, value: dict[str, Any]) -> PersonalDetails:
        addresses = tuple(
            address
            for item in (value.get("deliveryAddressList") or [])
            if (address := Address.from_api(item)) is not None
        )
        return cls(
            email=value["email"],
            phone=value.get("phone"),
            account_type=value.get("accountType"),
            invoice_address=Address.from_api(value.get("invoiceAddress")),
            delivery_addresses=addresses,
            default_payment=value.get("defaultPayment"),
            vat_number=value.get("vatNumber"),
            vat_status=value.get("vatStatus"),
        )


@dataclass(frozen=True, slots=True)
class OrderSummary:
    number: str
    date: str
    item_count: int
    status: str
    detail_url: str


@dataclass(frozen=True, slots=True)
class OrderItem:
    title: str
    product_url: str | None = None
    product_page_id: str | None = None
    image_url: str | None = None
    item_number: str | None = None
    options: dict[str, str] = field(default_factory=dict)
    shipped_quantity: int | None = None
    unit_price: str | None = None
    total_price: str | None = None


@dataclass(frozen=True, slots=True)
class OrderDetails:
    number: str
    date: str
    status: str
    items: tuple[OrderItem, ...]
    delivery_time: str | None = None
    tracking_codes: tuple[str, ...] = ()
    tracking_urls: tuple[str, ...] = ()
    payment_method: str | None = None
    amount: str | None = None
    invoice_address: str | None = None
    delivery_address: str | None = None
    payment_status: str | None = None
