import pytest

from bike24.errors import ParseError
from bike24.parsers import parse_order_details, parse_order_list

ORDER_LIST_HTML = """
<div class="order-list">
  <ul class="order-list__list">
    <li class="order-list__list-item">
      <div class="order">
        <div class="order__order-number">123456789</div>
        <div class="order__order-date">2026-07-17 20:46</div>
        <div class="order__number-of-items">2</div>
        <div class="order__status">Shipped</div>
        <div class="order__detail">
          <a class="order__detail-link" href="/my-account/orderlist/123456789">
            Show details
          </a>
        </div>
      </div>
    </li>
    <li class="order-list__list-item">
      <div class="order">
        <div class="order__order-number">987654321</div>
        <div class="order__order-date">2026-07-01 10:15</div>
        <div class="order__number-of-items">1</div>
        <div class="order__status">Processing</div>
        <div class="order__detail">
          <a class="order__detail-link" href="/my-account/orderlist/987654321">
            Show details
          </a>
        </div>
      </div>
    </li>
  </ul>
</div>
"""

BROKEN_ORDER_LIST_HTML = """
<div class="order-list">
  <ul class="order-list__list">
    <li class="new-order-row">Changed site markup</li>
  </ul>
</div>
"""

EMPTY_ORDER_LIST_HTML = """
<div class="order-list">
  <div class="order-list__empty">No orders yet</div>
</div>
"""


ORDER_DETAILS_HTML = """
<div class="order-detail">
  <div class="order-detail__overview">
    <div class="order-detail-overview">
      <div class="order-detail-overview__summary">
        <div class="order-detail-overview-item">
          <h3 class="order-detail-overview-item__title">Order-No.</h3>
          <div class="order-detail-overview-item__content">123456789</div>
        </div>
        <div class="order-detail-overview-item">
          <h3 class="order-detail-overview-item__title">Date</h3>
          <div class="order-detail-overview-item__content">2026-07-17 20:46</div>
        </div>
        <div class="order-detail-overview-item">
          <h3 class="order-detail-overview-item__title">Delivery time</h3>
          <div class="order-detail-overview-item__content">3-5 working days</div>
        </div>
        <div class="order-detail-overview-item">
          <h3 class="order-detail-overview-item__title">Status</h3>
          <div class="order-detail-overview-item__content"><b>Shipped</b></div>
        </div>
        <div class="order-detail-overview-item">
          <h3 class="order-detail-overview-item__title">Tracking Code</h3>
          <div class="order-detail-overview-item__content">
            <ul class="order-detail-overview-tracking">
              <li>
                <a class="order-detail-overview-tracking__link"
                   href="https://carrier.example/track/ABC123">ABC123</a>
              </li>
            </ul>
          </div>
        </div>
        <div class="order-detail-overview-item">
          <h3 class="order-detail-overview-item__title">Payment method</h3>
          <div class="order-detail-overview-item__content">
            <svg><use href="/icons.svg#PAYMENT_VISA"></use></svg>
          </div>
        </div>
        <div class="order-detail-overview-item">
          <h3 class="order-detail-overview-item__title">Amount</h3>
          <div class="order-detail-overview-item__content"><b>248,28 €</b></div>
        </div>
      </div>
      <div class="order-detail-overview-address">
        <div class="section-title">Invoice address</div>
        <p class="order-detail-overview-address__text">
          Test Person<br>1 Example Street<br>12345 Example
        </p>
      </div>
      <div class="order-detail-overview-address">
        <div class="section-title">Delivery address</div>
        <p class="order-detail-overview-address__text">
          Corresponds to my billing address
        </p>
      </div>
    </div>
  </div>
  <div class="order-detail__lists">
    <div class="order-detail-item">
      <div class="order-detail-item__inner">
        <a href="https://www.bike24.com/p2839528.html?origin=ACOL">
          <img class="order-detail-item__image" src="https://images.example/item.jpg">
        </a>
        <div class="order-detail-item__info">
          <p class="order-detail-item__title">
            <a href="https://www.bike24.com/p2839528.html?origin=ACOL">
              Example Cycling Shoes
            </a>
          </p>
          <div class="order-detail-item__options">
            <ul class="product-options">
              <li class="product-options__option">
                <label class="product-options__label">
                  Shoe Size EU: <span class="text--lead">47</span>
                </label>
              </li>
              <li class="product-options__option">
                <label class="product-options__label">
                  Item No.: <span class="text--lead">ABC123</span>
                </label>
              </li>
            </ul>
          </div>
        </div>
        <div class="order-detail-item__properties">
          <div class="order-detail-item__property">Shipped: <b>1</b></div>
          <div class="order-detail-item__property">245,79 €</div>
          <div class="order-detail-item__property"><b>245,79 €</b></div>
        </div>
      </div>
    </div>
    <div class="order-detail-item">
      <div class="order-detail-item__inner">
        <div class="order-detail-item__info order-detail-item__info--non-product">
          <p class="order-detail-item__title">Shipping and Handling</p>
        </div>
        <div class="order-detail-item__properties">
          <div class="order-detail-item__property"></div>
          <div class="order-detail-item__property"></div>
          <div class="order-detail-item__property"><b>2,49 €</b></div>
        </div>
      </div>
    </div>
  </div>
  <div class="order-detail__summary">
    <div><span>Payment status:</span><span>Paid</span></div>
  </div>
</div>
"""


def test_parse_order_list() -> None:
    orders = parse_order_list(ORDER_LIST_HTML)

    assert len(orders) == 2
    assert orders[0].number == "123456789"
    assert orders[0].date == "2026-07-17 20:46"
    assert orders[0].item_count == 2
    assert orders[0].status == "Shipped"
    assert orders[0].detail_url.endswith("/my-account/orderlist/123456789")
    assert orders[1].number == "987654321"


def test_parse_order_list_recognizes_explicit_empty_state() -> None:
    assert parse_order_list(EMPTY_ORDER_LIST_HTML) == []


def test_parse_order_list_rejects_missing_shell() -> None:
    with pytest.raises(ParseError, match="Could not find"):
        parse_order_list("<main>Account</main>")


def test_parse_order_list_rejects_unknown_row_markup() -> None:
    with pytest.raises(ParseError, match="no recognizable rows"):
        parse_order_list(BROKEN_ORDER_LIST_HTML)


def test_parse_order_details_and_skip_shipping_line() -> None:
    order = parse_order_details(ORDER_DETAILS_HTML)

    assert order.number == "123456789"
    assert order.date == "2026-07-17 20:46"
    assert order.status == "Shipped"
    assert order.delivery_time == "3-5 working days"
    assert order.tracking_codes == ("ABC123",)
    assert order.tracking_urls == ("https://carrier.example/track/ABC123",)
    assert order.payment_method == "VISA"
    assert order.amount == "248,28 €"
    assert order.invoice_address == "Test Person 1 Example Street 12345 Example"
    assert order.delivery_address == "Corresponds to my billing address"
    assert order.payment_status == "Paid"

    assert len(order.items) == 1
    item = order.items[0]
    assert item.title == "Example Cycling Shoes"
    assert item.product_url == "https://www.bike24.com/p2839528.html?origin=ACOL"
    assert item.product_page_id == "2839528"
    assert item.item_number == "ABC123"
    assert item.options == {"Shoe Size EU": "47"}
    assert item.shipped_quantity == 1
    assert item.unit_price == "245,79 €"
    assert item.total_price == "245,79 €"


def test_parse_order_details_rejects_missing_root() -> None:
    with pytest.raises(ParseError, match="Could not find BIKE24 order details"):
        parse_order_details("<main>Account</main>")


def test_parse_order_details_rejects_missing_line_items() -> None:
    html = ORDER_DETAILS_HTML.replace(
        '<div class="order-detail__lists">',
        '<div class="order-detail__lists" hidden>',
    )
    start = html.index('<div class="order-detail__lists" hidden>')
    end = html.index('<div class="order-detail__summary">')
    html = html[:start] + html[end:]

    with pytest.raises(ParseError, match="no line items"):
        parse_order_details(html)


def test_parse_order_details_rejects_malformed_product_line() -> None:
    html = ORDER_DETAILS_HTML.replace(
        '<div class="order-detail-item__info">',
        '<div class="changed-product-info">',
        1,
    )

    with pytest.raises(ParseError, match="missing product information"):
        parse_order_details(html)
