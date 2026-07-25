# Agent instructions

- Keep the client read-only; login is its only intentional non-GET request.
- Use headed Chrome.
- Never log or commit credentials or live account data. Live checks report
  aggregates only.
- Fail on unknown markup; accept only explicit empty states.
- Reset authentication after close or authentication failure.

Before handoff:

```shell
uv run pytest -q
uvx ruff check .
uvx ruff format --check .
git diff --check
```

Before publishing, also run `uv build` and a sanitized live smoke test covering
profile, orders, one detail, and reuse after `close()`. Confirm `.env` is
ignored and mode `600`.

Never commit or push unless explicitly asked.
