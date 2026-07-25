"""Authenticated, read-only BIKE24 client."""

from __future__ import annotations

import os
from collections.abc import Callable
from os import PathLike
from typing import Any, Protocol, Self, TypeVar

from dotenv import dotenv_values

from .browser import ChromeBackend
from .errors import AuthenticationError, Bike24Error
from .models import OrderDetails, OrderSummary, PersonalDetails
from .parsers import parse_order_details, parse_order_list

T = TypeVar("T")


class Backend(Protocol):
    def login(self, username: str, password: str) -> None: ...

    def get_json(self, path: str) -> dict[str, Any]: ...

    def get_html(self, path: str) -> str: ...

    def close(self) -> None: ...


class Bike24Client:
    """Read personal and order data from a BIKE24 customer account.

    BIKE24 puts its login behind a JavaScript anti-bot check, so the default
    backend opens a real local Chrome window. The client itself only submits
    the login form and performs GET requests.
    """

    def __init__(
        self,
        username: str,
        password: str,
        *,
        timeout: float = 30.0,
        browser_channel: str = "chrome",
        headless: bool = False,
        backend: Backend | None = None,
    ) -> None:
        if not username or not password:
            raise ValueError("username and password are required")
        self._username = username
        self._password = password
        self._backend = backend or ChromeBackend(
            timeout=timeout,
            browser_channel=browser_channel,
            headless=headless,
        )
        self._authenticated = False

    @classmethod
    def from_env(
        cls,
        *,
        env_file: str | PathLike[str] = ".env",
        **kwargs: Any,
    ) -> Bike24Client:
        file_values = dotenv_values(env_file)
        username = os.getenv("BIKE24_USERNAME") or file_values.get("BIKE24_USERNAME")
        password = os.getenv("BIKE24_PASSWORD") or file_values.get("BIKE24_PASSWORD")
        if not username or not password:
            raise ValueError(
                "Set BIKE24_USERNAME and BIKE24_PASSWORD (or add them to .env)"
            )
        return cls(username, password, **kwargs)

    def _ensure_authenticated(self) -> None:
        if not self._authenticated:
            self.login()

    def _authenticated_call(self, operation: Callable[[], T]) -> T:
        self._ensure_authenticated()
        try:
            return operation()
        except AuthenticationError:
            self._authenticated = False
            raise

    def login(self) -> None:
        self._authenticated = False
        try:
            self._backend.login(self._username, self._password)
        except AuthenticationError:
            self._authenticated = False
            raise
        self._authenticated = True

    def get_personal_details(self) -> PersonalDetails:
        data = self._authenticated_call(
            lambda: self._backend.get_json("/api/v2/user-account")
        )
        if not data.get("email"):
            raise Bike24Error("BIKE24 personal-details response is missing an email")
        return PersonalDetails.from_api(data)

    def list_orders(self, *, limit: int | None = None) -> list[OrderSummary]:
        if limit is not None and limit < 0:
            raise ValueError("limit must be zero or greater")
        html = self._authenticated_call(
            lambda: self._backend.get_html("/my-account/orderlist")
        )
        orders = parse_order_list(html)
        return orders[:limit] if limit is not None else orders

    def get_order(self, order_number: str | int) -> OrderDetails:
        normalized = str(order_number)
        if not normalized.isdecimal():
            raise ValueError("order_number must contain digits only")
        html = self._authenticated_call(
            lambda: self._backend.get_html(f"/my-account/orderlist/{normalized}")
        )
        order = parse_order_details(html)
        if order.number != normalized:
            raise Bike24Error(
                f"BIKE24 returned order {order.number!r}, expected {normalized!r}"
            )
        return order

    def close(self) -> None:
        self._authenticated = False
        self._backend.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
