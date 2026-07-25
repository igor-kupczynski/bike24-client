"""Browser-backed transport used to pass BIKE24's JavaScript edge checks."""

from __future__ import annotations

import json
import os
from typing import Any, ClassVar
from urllib.parse import urljoin, urlparse

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)
from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from .constants import BASE_URL
from .errors import AuthenticationError, Bike24Error


class ChromeBackend:
    """Perform the small, fixed set of reads through a real Chrome process."""

    _ALLOWED_HOSTS: ClassVar[frozenset[str]] = frozenset(
        {"www.bike24.com", "assets.bike24.com"}
    )

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        browser_channel: str = "chrome",
        headless: bool = False,
    ) -> None:
        self._timeout_ms = timeout * 1_000
        self._browser_channel = browser_channel
        self._headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def _url(self, path: str) -> str:
        return urljoin(f"{BASE_URL}/", path.lstrip("/"))

    def _start(self) -> Page:
        if self._page is not None:
            return self._page
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(
                channel=self._browser_channel,
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key not in {"BIKE24_USERNAME", "BIKE24_PASSWORD"}
                },
            )
            self._context = self._browser.new_context(locale="en-US")
            self._context.set_default_timeout(self._timeout_ms)
            self._context.set_default_navigation_timeout(self._timeout_ms)
            self._context.route("**/*", self._route_request)
            self._page = self._context.new_page()
            return self._page
        except Exception:
            self.close()
            raise

    def _route_request(self, route: Any) -> None:
        request = route.request
        host = urlparse(request.url).hostname
        if host not in self._ALLOWED_HOSTS or request.resource_type in {
            "font",
            "image",
            "media",
        }:
            route.abort()
        else:
            route.continue_()

    def _goto(self, path: str) -> Page:
        page = self._start()
        response = page.goto(
            self._url(path),
            wait_until="domcontentloaded",
            timeout=self._timeout_ms,
        )
        if response is None:
            raise Bike24Error(f"BIKE24 did not respond for {path}")
        if response.status >= 400:
            raise Bike24Error(f"BIKE24 returned HTTP {response.status} for {path}")
        if urlparse(page.url).path == "/login.html" and path != "/login.html":
            raise AuthenticationError("BIKE24 session is not authenticated")
        return page

    def login(self, username: str, password: str) -> None:
        page = self._goto("/login.html")
        form = page.locator('form[action="/login.html"]')
        if form.count() != 1:
            mode = "headless Chrome" if self._headless else self._browser_channel
            raise AuthenticationError(
                f"BIKE24 blocked the login page in {mode}; use headed Chrome"
            )

        decline = page.get_by_role("button", name="Decline", exact=True)
        if decline.count() == 1 and decline.is_visible():
            decline.click()

        form.locator('input[name="username"]').fill(username)
        form.locator('input[name="password"]').fill(password)
        form.get_by_role("button", name="LOG IN", exact=True).click()
        try:
            page.wait_for_url(
                "**/my-account**",
                wait_until="domcontentloaded",
                timeout=self._timeout_ms,
            )
        except PlaywrightTimeoutError as exc:
            raise AuthenticationError(
                "BIKE24 rejected the credentials or requested an interactive check"
            ) from exc

    def get_json(self, path: str) -> dict[str, Any]:
        page = self._start()
        result = page.evaluate(
            """async (url) => {
                const response = await fetch(url, {
                    method: "GET",
                    credentials: "include",
                    headers: {
                        "Accept": "application/json",
                        "X-Requested-With": "XMLHttpRequest"
                    }
                });
                return {
                    status: response.status,
                    url: response.url,
                    contentType: response.headers.get("content-type") || "",
                    text: await response.text()
                };
            }""",
            self._url(path),
        )
        if result["status"] >= 400:
            raise Bike24Error(f"BIKE24 returned HTTP {result['status']} for {path}")
        if urlparse(result["url"]).path == "/login.html":
            raise AuthenticationError("BIKE24 session is not authenticated")
        if "json" not in result["contentType"].casefold():
            raise Bike24Error(f"BIKE24 did not return JSON for {path}")
        try:
            value = json.loads(result["text"])
        except (TypeError, ValueError) as exc:
            raise Bike24Error(f"BIKE24 returned invalid JSON for {path}") from exc
        if not isinstance(value, dict):
            raise Bike24Error(f"BIKE24 returned unexpected JSON for {path}")
        return value

    def get_html(self, path: str) -> str:
        return self._goto(path).content()

    def close(self) -> None:
        context, browser, playwright = (
            self._context,
            self._browser,
            self._playwright,
        )
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

        first_error: Exception | None = None
        for resource in (context, browser, playwright):
            if resource is None:
                continue
            try:
                if resource is playwright:
                    resource.stop()
                else:
                    resource.close()
            except PlaywrightError as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error
