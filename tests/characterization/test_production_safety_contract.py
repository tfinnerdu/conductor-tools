"""Characterization tests — Production-Safety UI Contract.

Pins the in-app production-safety surfaces:

  - The app shell carries the standing production-safety banner
    (#env-warning-banner) — this console always acts on a real Conductor.
  - Every destructive surface (Settings/Secrets, Reconciler, Migrations,
    Test Harness) carries a .live-warning callout — four in total.

If a callout is dropped or the banner is removed, a caustic operation has
lost its visible warning. See warning.md for the catalogue of caustic
operations these surfaces guard.

If an assertion fails due to an intentional change, update the hardcoded
values AND this comment to record when and why.
Last verified: 2026-05-22.
"""


class TestProductionSafetyBannerCharacterization:
    """Characterization: the standing production-safety banner."""

    def test_app_shell_has_safety_banner_characterization(self, client):
        """
        CONTRACT: the app shell renders the production-safety banner element
        (#env-warning-banner). It warns that state-changing actions take
        effect immediately against a real Conductor.
        """
        resp = client.get("/")
        html = resp.get_data(as_text=True)
        assert 'id="env-warning-banner"' in html, (
            "App shell is missing the #env-warning-banner production-safety "
            "banner. It is a standing reminder that this console acts on a "
            "real Conductor."
        )


class TestLiveWarningCalloutsCharacterization:
    """Characterization: per-section destructive-action warnings."""

    def test_destructive_panels_each_carry_a_live_warning_characterization(self, client):
        """
        CONTRACT: every destructive surface (Settings/Secrets, Reconciler,
        Migrations, Test Harness) carries a .live-warning callout. There are
        four such surfaces; if this count changes, a destructive surface has
        gained or lost its inline warning — see warning.md.
        """
        resp = client.get("/")
        html = resp.get_data(as_text=True)
        # Prefix match — the callouts ship as `class="live-warning d-none"`
        # and are revealed by app.js when SHOW_MOCK is off.
        count = html.count('class="live-warning')
        assert count == 4, (
            f"Expected 4 .live-warning callouts (Settings, Reconciler, "
            f"Migrations, Test Harness), found {count}. A destructive surface "
            "may have gained or lost its inline warning — see warning.md."
        )
