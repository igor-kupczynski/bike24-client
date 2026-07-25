"""Client-specific exceptions."""


class Bike24Error(Exception):
    """Base exception for BIKE24 client errors."""


class AuthenticationError(Bike24Error):
    """Raised when BIKE24 rejects the supplied credentials."""


class ParseError(Bike24Error):
    """Raised when a BIKE24 page no longer matches the expected structure."""
