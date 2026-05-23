"""Environment helpers."""
import os


def show_mock() -> bool:
    """Return True when SHOW_MOCK is enabled.

    Mock data is OPT-IN. With SHOW_MOCK unset (the default), every integration
    performs the real call and surfaces real errors. Set SHOW_MOCK=1 / true /
    yes to enable fixture data for offline testing.

    The flag is read per call so it can be flipped without restarting.
    """
    return os.environ.get("SHOW_MOCK", "").strip().lower() in ("1", "true", "yes", "on")
