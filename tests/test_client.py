from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from bike24.client import Bike24Client
from bike24.errors import AuthenticationError, Bike24Error, ParseError
from bike24.models import PersonalDetails

from .test_parsers import (
    BROKEN_ORDER_LIST_HTML,
    ORDER_DETAILS_HTML,
    ORDER_LIST_HTML,
)


class FakeBackend:
    def __init__(
        self,
        *,
        profile: dict[str, Any] | None = None,
        order_list_html: str = ORDER_LIST_HTML,
        order_details_html: str = ORDER_DETAILS_HTML,
    ) -> None:
        self.profile = profile or {
            "email": "person@example.com",
            "phone": "+123",
            "accountType": "private",
            "invoiceAddress": {
                "firstName": "Test",
                "lastName": "Person",
            },
            "deliveryAddressList": [],
        }
        self.order_list_html = order_list_html
        self.order_details_html = order_details_html
        self.login_count = 0
        self.close_count = 0
        self.credentials: tuple[str, str] | None = None
        self.get_paths: list[str] = []
        self.login_error: AuthenticationError | None = None
        self.read_error: AuthenticationError | None = None

    def login(self, username: str, password: str) -> None:
        self.login_count += 1
        self.credentials = (username, password)
        if self.login_error is not None:
            raise self.login_error

    def get_json(self, path: str) -> dict[str, Any]:
        self.get_paths.append(path)
        if self.read_error is not None:
            error, self.read_error = self.read_error, None
            raise error
        return self.profile

    def get_html(self, path: str) -> str:
        self.get_paths.append(path)
        if self.read_error is not None:
            error, self.read_error = self.read_error, None
            raise error
        if path == "/my-account/orderlist":
            return self.order_list_html
        return self.order_details_html

    def close(self) -> None:
        self.close_count += 1


def test_client_profile_orders_details_paths_and_context_close() -> None:
    backend = FakeBackend()

    with Bike24Client("person@example.com", "secret", backend=backend) as client:
        profile = client.get_personal_details()
        orders = client.list_orders(limit=1)
        order = client.get_order("123456789")

    assert profile.email == "person@example.com"
    assert [item.number for item in orders] == ["123456789"]
    assert order.items[0].item_number == "ABC123"
    assert backend.login_count == 1
    assert backend.get_paths == [
        "/api/v2/user-account",
        "/my-account/orderlist",
        "/my-account/orderlist/123456789",
    ]
    assert backend.close_count == 1


def test_close_forces_login_when_client_is_reused() -> None:
    backend = FakeBackend()
    client = Bike24Client("person@example.com", "secret", backend=backend)

    client.get_personal_details()
    client.close()
    client.get_personal_details()

    assert backend.login_count == 2
    assert backend.close_count == 1


def test_authentication_error_during_read_forces_next_call_to_login() -> None:
    backend = FakeBackend()
    backend.read_error = AuthenticationError("expired")
    client = Bike24Client("person@example.com", "secret", backend=backend)

    with pytest.raises(AuthenticationError, match="expired"):
        client.get_personal_details()
    assert backend.login_count == 1

    assert client.get_personal_details().email == "person@example.com"
    assert backend.login_count == 2


def test_authentication_error_during_login_is_retried() -> None:
    backend = FakeBackend()
    backend.login_error = AuthenticationError("rejected")
    client = Bike24Client("person@example.com", "secret", backend=backend)

    with pytest.raises(AuthenticationError, match="rejected"):
        client.get_personal_details()

    backend.login_error = None
    assert client.get_personal_details().email == "person@example.com"
    assert backend.login_count == 2


def test_from_env_loads_dotenv_without_mutating_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BIKE24_USERNAME=dotenv@example.com\nBIKE24_PASSWORD=dotenv-secret\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("BIKE24_USERNAME", raising=False)
    monkeypatch.delenv("BIKE24_PASSWORD", raising=False)
    backend = FakeBackend()

    client = Bike24Client.from_env(env_file=env_file, backend=backend)
    client.get_personal_details()

    assert backend.credentials == ("dotenv@example.com", "dotenv-secret")
    assert "BIKE24_USERNAME" not in __import__("os").environ
    assert "BIKE24_PASSWORD" not in __import__("os").environ


def test_from_env_prefers_existing_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BIKE24_USERNAME=file@example.com\nBIKE24_PASSWORD=file-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BIKE24_USERNAME", "environment@example.com")
    monkeypatch.setenv("BIKE24_PASSWORD", "environment-secret")
    backend = FakeBackend()

    client = Bike24Client.from_env(env_file=env_file, backend=backend)
    client.get_personal_details()

    assert backend.credentials == ("environment@example.com", "environment-secret")


def test_from_env_rejects_missing_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BIKE24_USERNAME", raising=False)
    monkeypatch.delenv("BIKE24_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="BIKE24_USERNAME"):
        Bike24Client.from_env(env_file=tmp_path / "missing.env")


def test_missing_profile_email_raises_bike24_error() -> None:
    client = Bike24Client(
        "user", "password", backend=FakeBackend(profile={"phone": "1"})
    )

    with pytest.raises(Bike24Error, match="missing an email"):
        client.get_personal_details()


def test_parser_error_propagates_through_client() -> None:
    client = Bike24Client(
        "user",
        "password",
        backend=FakeBackend(order_list_html=BROKEN_ORDER_LIST_HTML),
    )

    with pytest.raises(ParseError, match="no recognizable rows"):
        client.list_orders()


def test_order_number_mismatch_raises_bike24_error() -> None:
    client = Bike24Client("user", "password", backend=FakeBackend())

    with pytest.raises(Bike24Error, match="expected '999999999'"):
        client.get_order("999999999")


def test_create_return_form_fetches_order_and_profile(tmp_path: Path) -> None:
    backend = FakeBackend()
    client = Bike24Client("user", "password", backend=backend)
    output = tmp_path / "return.pdf"

    result = client.create_return_form("123456789", output)

    assert result == output.resolve()
    assert output.exists()
    assert backend.get_paths == [
        "/my-account/orderlist/123456789",
        "/api/v2/user-account",
    ]


def test_list_order_limits() -> None:
    client = Bike24Client("user", "password", backend=FakeBackend())

    assert [order.number for order in client.list_orders()] == [
        "123456789",
        "987654321",
    ]
    assert [order.number for order in client.list_orders(limit=1)] == ["123456789"]
    assert client.list_orders(limit=0) == []


def test_personal_details_accepts_null_and_multiple_delivery_addresses() -> None:
    no_addresses = PersonalDetails.from_api(
        {"email": "person@example.com", "deliveryAddressList": None}
    )
    multiple_addresses = PersonalDetails.from_api(
        {
            "email": "person@example.com",
            "deliveryAddressList": [
                {"id": "first", "firstName": "One"},
                {"id": "second", "firstName": "Two"},
            ],
        }
    )

    assert no_addresses.delivery_addresses == ()
    assert [address.id for address in multiple_addresses.delivery_addresses] == [
        "first",
        "second",
    ]


def test_order_number_rejects_non_digits() -> None:
    client = Bike24Client("person@example.com", "secret", backend=FakeBackend())

    with pytest.raises(ValueError, match="digits only"):
        client.get_order("../checkout")


def test_negative_limit_is_rejected() -> None:
    client = Bike24Client("person@example.com", "secret", backend=FakeBackend())

    with pytest.raises(ValueError, match="zero or greater"):
        client.list_orders(limit=-1)
