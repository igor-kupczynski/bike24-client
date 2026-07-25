from __future__ import annotations

import json
from typing import Any, Self

import pytest

from bike24 import cli
from bike24.errors import AuthenticationError
from bike24.models import OrderDetails, OrderItem, OrderSummary, PersonalDetails


class StubClient:
    result: Any
    error: Exception | None = None
    received_limit: int | None = None
    received_order_number: str | None = None
    closed = False

    @classmethod
    def from_env(cls) -> StubClient:
        return cls()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        type(self).closed = True

    def _result(self) -> Any:
        if type(self).error is not None:
            raise type(self).error
        return type(self).result

    def get_personal_details(self) -> PersonalDetails:
        return self._result()

    def list_orders(self, *, limit: int | None = None) -> list[OrderSummary]:
        type(self).received_limit = limit
        return self._result()

    def get_order(self, order_number: str) -> OrderDetails:
        type(self).received_order_number = order_number
        return self._result()


@pytest.fixture(autouse=True)
def stub_client(monkeypatch: pytest.MonkeyPatch) -> None:
    StubClient.error = None
    StubClient.result = None
    StubClient.received_limit = None
    StubClient.received_order_number = None
    StubClient.closed = False
    monkeypatch.setattr(cli, "Bike24Client", StubClient)


def test_profile_command_emits_json(capsys: pytest.CaptureFixture[str]) -> None:
    StubClient.result = PersonalDetails(email="person@example.com")

    assert cli.main(["profile"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["email"] == "person@example.com"
    assert StubClient.closed


def test_orders_command_passes_limit_and_emits_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    StubClient.result = [
        OrderSummary(
            number="123",
            date="2026-01-01",
            item_count=1,
            status="Shipped",
            detail_url="https://www.bike24.com/my-account/orderlist/123",
        )
    ]

    assert cli.main(["orders", "--limit", "1"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert StubClient.received_limit == 1
    assert payload[0]["number"] == "123"


def test_orders_command_emits_empty_list(capsys: pytest.CaptureFixture[str]) -> None:
    StubClient.result = []

    assert cli.main(["orders"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_order_command_emits_items(capsys: pytest.CaptureFixture[str]) -> None:
    StubClient.result = OrderDetails(
        number="123",
        date="2026-01-01",
        status="Shipped",
        items=(OrderItem(title="Test item", item_number="ITEM1"),),
    )

    assert cli.main(["order", "123"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert StubClient.received_order_number == "123"
    assert payload["items"][0]["item_number"] == "ITEM1"


def test_cli_reports_public_errors_and_nonzero_exit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    StubClient.error = AuthenticationError("login rejected")

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["profile"])

    assert exc_info.value.code == 1
    assert capsys.readouterr().err == "bike24: error: login rejected\n"
