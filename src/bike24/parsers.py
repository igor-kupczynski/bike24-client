"""HTML parsers for BIKE24's account pages."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .constants import BASE_URL
from .errors import ParseError
from .models import OrderDetails, OrderItem, OrderSummary

_PRODUCT_ID_RE = re.compile(r"/p(\d+)\.html")
_INTEGER_RE = re.compile(r"\d+")
_EMPTY_ORDER_TEXT_RE = re.compile(
    r"\b(?:no orders|no order history|haven['’]t placed any orders)\b",
    re.IGNORECASE,
)


def _text(node: Tag | None) -> str:
    return " ".join(node.stripped_strings) if node else ""


def _required_text(root: Tag, selector: str, field: str) -> str:
    value = _text(root.select_one(selector))
    if not value:
        raise ParseError(f"Could not find {field!r} in BIKE24 HTML")
    return value


def parse_order_list(html: str, *, base_url: str = BASE_URL) -> list[OrderSummary]:
    soup = BeautifulSoup(html, "html.parser")
    shell = soup.select_one(".order-list")
    if shell is None:
        raise ParseError("Could not find the BIKE24 order list")

    orders: list[OrderSummary] = []

    for row in shell.select(".order-list__list-item .order"):
        number = _required_text(row, ".order__order-number", "order number")
        date = _required_text(row, ".order__order-date", "order date")
        count_text = _required_text(row, ".order__number-of-items", "item count")
        status = _required_text(row, ".order__status", "order status")
        link = row.select_one("a.order__detail-link[href]")
        if not link:
            raise ParseError(f"Could not find detail link for order {number}")

        count_match = _INTEGER_RE.search(count_text)
        if not count_match:
            raise ParseError(f"Invalid item count for order {number}: {count_text!r}")

        orders.append(
            OrderSummary(
                number=number,
                date=date,
                item_count=int(count_match.group()),
                status=status,
                detail_url=urljoin(base_url, str(link["href"])),
            )
        )

    if not orders:
        empty_state = shell.select_one(
            ".order-list__empty, .order-list__empty-state, "
            '[data-testid="order-list-empty"]'
        )
        if empty_state is not None or _EMPTY_ORDER_TEXT_RE.search(_text(shell)):
            return []
        raise ParseError(
            "BIKE24 order list contained no recognizable rows or empty-state marker"
        )
    return orders


def _overview_fields(soup: BeautifulSoup) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in soup.select(".order-detail-overview-item"):
        title = _text(item.select_one(".order-detail-overview-item__title")).rstrip(":")
        content = _text(item.select_one(".order-detail-overview-item__content"))
        if title and content:
            result[title] = content
    return result


def _item_options(item: Tag) -> tuple[dict[str, str], str | None]:
    options: dict[str, str] = {}
    item_number: str | None = None
    for option in item.select(".product-options__option"):
        label_node = option.select_one(".product-options__label")
        value_node = option.select_one(".text--lead")
        label = _text(label_node)
        value = _text(value_node)

        if label and value and label.endswith(value):
            label = label[: -len(value)].rstrip().rstrip(":")
        else:
            label = label.rstrip(":")

        # On BIKE24 the label may contain the whole "Label: Value" string.
        if label and not value and ":" in _text(label_node):
            label, value = (part.strip() for part in _text(label_node).split(":", 1))
        if label and value:
            if label.casefold() in {"item no.", "item no", "item number"}:
                item_number = value
            else:
                options[label] = value
    return options, item_number


def _parse_order_item(item: Tag, *, base_url: str) -> OrderItem | None:
    info = item.select_one(".order-detail-item__info")
    if info is not None and "order-detail-item__info--non-product" in info.get(
        "class", []
    ):
        return None
    if info is None:
        raise ParseError("Order line is missing product information")

    title = _required_text(item, ".order-detail-item__title", "item title")
    product_link = item.select_one(
        ".order-detail-item__title a[href]"
    ) or item.select_one('a[href*="/p"]')
    if product_link is None:
        raise ParseError(f"Order item {title!r} is missing its product link")
    product_url = urljoin(base_url, str(product_link["href"]))
    product_match = _PRODUCT_ID_RE.search(urlparse(product_url).path)
    if product_match is None:
        raise ParseError(f"Order item {title!r} has an invalid product link")

    image = item.select_one("img.order-detail-item__image")
    image_url = None
    if image:
        source = image.get("src") or image.get("data-src")
        if source:
            image_url = urljoin(base_url, str(source))

    options, item_number = _item_options(item)
    if not item_number:
        raise ParseError(f"Order item {title!r} is missing its item number")

    property_nodes = item.select(".order-detail-item__property")
    quantity_node = next(
        (node for node in property_nodes if "shipped" in _text(node).casefold()),
        None,
    )
    if quantity_node is None:
        raise ParseError(f"Order item {title!r} is missing shipped quantity")
    quantity_match = _INTEGER_RE.search(_text(quantity_node))
    if quantity_match is None:
        raise ParseError(f"Order item {title!r} has an invalid shipped quantity")

    total_node = next(
        (
            node
            for node in reversed(property_nodes)
            if node is not quantity_node and node.select_one("b") and _text(node)
        ),
        None,
    )
    unit_candidates = [
        node
        for node in property_nodes
        if node is not quantity_node and node is not total_node and _text(node)
    ]
    if total_node is None or len(unit_candidates) != 1:
        raise ParseError(f"Order item {title!r} has unrecognized price fields")

    return OrderItem(
        title=title,
        product_url=product_url,
        product_page_id=product_match.group(1),
        image_url=image_url,
        item_number=item_number,
        options=options,
        shipped_quantity=int(quantity_match.group()),
        unit_price=_text(unit_candidates[0]),
        total_price=_text(total_node),
    )


def _address_for_title(soup: BeautifulSoup, title: str) -> str | None:
    for block in soup.select(".order-detail-overview-address"):
        if _text(block.select_one(".section-title")).casefold() == title.casefold():
            return (
                _text(block.select_one(".order-detail-overview-address__text")) or None
            )
    return None


def _summary_value(soup: BeautifulSoup, label: str) -> str | None:
    summary = soup.select_one(".order-detail__summary")
    if not summary:
        return None
    label_folded = label.casefold()
    for node in summary.find_all(string=True):
        if label_folded in " ".join(node.split()).casefold():
            parent = node.parent
            if parent:
                sibling = parent.find_next_sibling()
                if sibling and _text(sibling):
                    return _text(sibling)
    return None


def parse_order_details(html: str, *, base_url: str = BASE_URL) -> OrderDetails:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".order-detail")
    if root is None:
        raise ParseError("Could not find BIKE24 order details")

    overview = _overview_fields(soup)
    number = overview.get("Order-No.")
    date = overview.get("Date")
    status = overview.get("Status")
    if not number or not date or not status:
        raise ParseError("Order details are missing number, date, or status")

    item_nodes = soup.select(".order-detail-item")
    if not item_nodes:
        raise ParseError("Order details contained no line items")
    items = tuple(
        parsed
        for node in item_nodes
        if (parsed := _parse_order_item(node, base_url=base_url)) is not None
    )
    tracking_links = soup.select(".order-detail-overview-tracking__link[href]")
    tracking_codes = tuple(_text(link) for link in tracking_links if _text(link))
    tracking_urls = tuple(
        urljoin(base_url, str(link["href"])) for link in tracking_links
    )

    payment_method = overview.get("Payment method")
    if not payment_method:
        payment_node = next(
            (
                item
                for item in soup.select(".order-detail-overview-item")
                if _text(item.select_one(".order-detail-overview-item__title"))
                == "Payment method"
            ),
            None,
        )
        payment_icon = (
            payment_node.select_one("use[href], use[xlink\\:href]")
            if payment_node
            else None
        )
        if payment_icon:
            icon_ref = payment_icon.get("href") or payment_icon.get("xlink:href") or ""
            payment_method = (
                str(icon_ref).split("#")[-1].removeprefix("PAYMENT_") or None
            )

    return OrderDetails(
        number=number,
        date=date,
        status=status,
        items=items,
        delivery_time=overview.get("Delivery time"),
        tracking_codes=tracking_codes,
        tracking_urls=tracking_urls,
        payment_method=payment_method,
        amount=overview.get("Amount"),
        invoice_address=_address_for_title(soup, "Invoice address"),
        delivery_address=_address_for_title(soup, "Delivery address"),
        payment_status=_summary_value(soup, "Payment status"),
    )
