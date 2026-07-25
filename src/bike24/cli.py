"""Command-line interface for the BIKE24 client."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .client import Bike24Client
from .errors import Bike24Error


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bike24",
        description="Read personal and order data from your BIKE24 account.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("profile", help="Show personal account details")

    orders = subparsers.add_parser("orders", help="List recent orders")
    orders.add_argument("--limit", type=int, help="Maximum number of orders")

    order = subparsers.add_parser("order", help="Show one order and its items")
    order.add_argument("order_number", help="BIKE24 order number")

    return_form = subparsers.add_parser(
        "return-form",
        help="Create an editable return form from an order",
    )
    return_form.add_argument("order_number", help="BIKE24 order number")
    return_form.add_argument(
        "--item",
        dest="item_numbers",
        action="append",
        help="Item number to include; repeat to select multiple (default: all)",
    )
    return_form.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output PDF (default: BIKE24_return_ORDER_NUMBER.pdf)",
    )
    return_form.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing output file",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with Bike24Client.from_env() as client:
            if args.command == "profile":
                result: Any = client.get_personal_details()
            elif args.command == "orders":
                result = client.list_orders(limit=args.limit)
            elif args.command == "return-form":
                output = args.output or Path(f"BIKE24_return_{args.order_number}.pdf")
                path = client.create_return_form(
                    args.order_number,
                    output,
                    item_numbers=args.item_numbers,
                    overwrite=args.force,
                )
                result = {"path": str(path), "editable": True}
            else:
                result = client.get_order(args.order_number)
    except (Bike24Error, ValueError) as exc:
        parser.exit(1, f"bike24: error: {exc}\n")

    if isinstance(result, dict):
        payload = result
    elif isinstance(result, list):
        payload = [asdict(item) for item in result]
    else:
        payload = asdict(result)
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False, default=_json_default)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
