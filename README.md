# BIKE24 client

An unofficial, read-only Python client for your BIKE24 account. It can read:

- personal details and saved addresses;
- recent orders;
- products, quantities, options, and prices from an order.

It uses a visible Google Chrome window because BIKE24 blocks headless and
ordinary HTTP clients.

## Setup

Install [uv](https://docs.astral.sh/uv/) and Google Chrome, then run:

```shell
uv sync
cp .env.example .env
```

Add your BIKE24 login and password to `.env`. The file is ignored by Git.

## Use

Commands print JSON:

```shell
# Personal details
uv run bike24 profile

# Recent orders
uv run bike24 orders
uv run bike24 orders --limit 5

# One order with its products
uv run bike24 order ORDER_NUMBER
```

The JSON contains private account and purchase data. Handle it accordingly.

## Python

```python
from bike24 import Bike24Client

with Bike24Client.from_env() as client:
    profile = client.get_personal_details()
    orders = client.list_orders(limit=5)
    order = client.get_order(orders[0].number)
```

BIKE24 does not provide these interfaces as a public API, so site changes may
occasionally require client updates.

## Development

```shell
uv run pytest
```
