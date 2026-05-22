"""Characterization tests — Mock/Live Signal Contract.

Pins the response-header and UI-hook halves of the Mock/Live Signal standard:

  - X-Mock-Mode: "true" present on /api/ responses when mock mode is active
    (CONDUCTOR_URL unset/empty); absent when a live CONDUCTOR_URL is set.
  - The app shell exposes the DOM hooks that applyConductorEnvSignals() in
    app.js toggles (MOCK/LIVE chips, live-environment banner, per-section
    live-warning callouts).

The "mock" key in /api/v1/health/deep is pinned separately in
test_health_contract.py.

If any assertion fails due to an intentional change, update the hardcoded
values AND this comment to record when and why.
Last verified: 2026-05-22.
"""
import os
from unittest.mock import patch


KNOWN_MOCK_HEADER = "X-Mock-Mode"
KNOWN_MOCK_HEADER_VALUE = "true"
KNOWN_API_PROBE_PATH = "/api/v1/health"


class TestMockModeHeaderCharacterization:
    """Characterization: the X-Mock-Mode response header."""

    def test_header_present_in_mock_mode_characterization(self, client):
        """
        CONTRACT: X-Mock-Mode: true on /api/ responses when CONDUCTOR_URL is
        empty (mock mode). This is the response-header signal of the Mock/Live
        Signal standard — consumers detect fabricated data without parsing
        the response body.
        """
        with patch.dict(os.environ, {"CONDUCTOR_URL": ""}):
            resp = client.get(KNOWN_API_PROBE_PATH)
        assert resp.headers.get(KNOWN_MOCK_HEADER) == KNOWN_MOCK_HEADER_VALUE, (
            f"{KNOWN_MOCK_HEADER} must be '{KNOWN_MOCK_HEADER_VALUE}' on /api/ "
            f"responses in mock mode. Got '{resp.headers.get(KNOWN_MOCK_HEADER)}'. "
            "This is the Mock/Live Signal standard response-header signal."
        )

    def test_header_absent_in_live_mode_characterization(self, client):
        """
        CONTRACT: X-Mock-Mode is NOT set when a live CONDUCTOR_URL is
        configured. A stale header in live mode would tell consumers the data
        is fabricated when it is real.
        """
        with patch.dict(os.environ, {"CONDUCTOR_URL": "https://conductor.example.edu"}):
            resp = client.get(KNOWN_API_PROBE_PATH)
        assert KNOWN_MOCK_HEADER not in resp.headers, (
            f"{KNOWN_MOCK_HEADER} must be absent in live mode (CONDUCTOR_URL "
            f"set). Got '{resp.headers.get(KNOWN_MOCK_HEADER)}'."
        )

    def test_header_scoped_to_api_routes_characterization(self, client):
        """
        CONTRACT: the standard scopes X-Mock-Mode to API responses. The HTML
        shell at / is a page route and must not carry the header.
        """
        with patch.dict(os.environ, {"CONDUCTOR_URL": ""}):
            resp = client.get("/")
        assert KNOWN_MOCK_HEADER not in resp.headers, (
            f"{KNOWN_MOCK_HEADER} must only appear on /api/ responses, not on "
            "HTML page routes."
        )


class TestLiveWarningUiHooksCharacterization:
    """Characterization: DOM hooks the env-signal JS depends on."""

    def test_app_shell_has_env_warning_hooks_characterization(self, client):
        """
        CONTRACT: the app shell exposes the DOM ids/classes that
        applyConductorEnvSignals() in app.js toggles. If a hook is renamed in
        the template without updating app.js, the live-environment warnings
        silently stop appearing — and a destructive surface loses its guard.
        """
        resp = client.get("/")
        html = resp.get_data(as_text=True)
        for hook in (
            'id="mock-mode-chip"',
            'id="live-mode-chip"',
            'id="env-warning-banner"',
            'class="live-warning',
        ):
            assert hook in html, (
                f"App shell is missing required env-signal DOM hook: {hook}. "
                "applyConductorEnvSignals() in app.js depends on it."
            )

    def test_destructive_panels_each_carry_a_live_warning_characterization(self, client):
        """
        CONTRACT: every destructive surface (Settings/Secrets, Reconciler,
        Migrations, Test Harness) carries a .live-warning callout. There are
        four such surfaces; if this count drops, a caustic operation has lost
        its inline warning. See warning.md.
        """
        resp = client.get("/")
        html = resp.get_data(as_text=True)
        count = html.count('class="live-warning')
        assert count == 4, (
            f"Expected 4 .live-warning callouts (Settings, Reconciler, "
            f"Migrations, Test Harness), found {count}. A destructive surface "
            "may have lost its inline warning — see warning.md."
        )
