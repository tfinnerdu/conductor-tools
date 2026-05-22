# ⚠ Production Testing — Caustic Operations

This document flags every spot in Conductor Companion that can have a
**detrimental effect on a real environment**. It exists because testing is
moving to production: the local instance has little data and there is no
dedicated dev/staging Conductor.

Read this before exercising any write/action surface against a live Conductor,
Salesforce, or Colleague.

---

## Are you in mock mode or live mode?

The app falls back to fabricated fixture data whenever `CONDUCTOR_URL` is unset.
With `CONDUCTOR_URL` pointed at a real instance, every action below hits that
instance for real. Three signals tell you which mode you are in:

| Signal | Mock mode | Live mode |
|---|---|---|
| Navbar chip | amber **MOCK** | green **LIVE** |
| Top-of-page banner | hidden | amber **LIVE environment** banner |
| `GET /api/v1/health/deep` body | `"mock": true` | `"mock": false` |
| API response header | `X-Mock-Mode: true` | header absent |

When live, each destructive section also shows an inline **⚠ LIVE** warning
callout, and destructive buttons raise a confirmation dialog that spells out the
production impact.

---

## Severity legend

- **CRITICAL** — irreversibly mutates external production state.
- **HIGH** — triggers real side effects (workers, outbound messages).
- **MEDIUM** — correctness/trust hazard; wrong or misleading data.
- **LOW** — configuration footgun; harmless if set correctly.

---

## CRITICAL — irreversible production mutations

### C1. Conductor secret create / update / delete
- **Where:** Settings tab → Conductor Secrets. `app/routes/secrets.py`,
  `ConductorClient.set_secret` / `delete_secret` (`PUT`/`DELETE /api/secrets/{name}`).
- **What happens:** writes straight to the production Conductor secret store.
  Every workflow referencing that secret picks up the new value on its next run.
- **Risk:** overwriting a secret with a test value, or deleting one, breaks
  every live workflow that uses it. There is no undo and no version history.
- **In-app safeguard:** inline LIVE warning + confirmation dialog naming the
  secret and the impact.
- **Before you test:** note the current value out-of-band first; never point
  the add/update form at a secret name that live workflows use.

### C2. Reconciler bulk retry / "Retry All"
- **Where:** Reconciler tab. `app/routes/reconciler.py` `bulk_retry` and the
  per-group "Retry All" button; `ConductorClient.retry_workflow`.
- **What happens:** re-runs failed workflow executions on the live Conductor —
  **up to 500 at once** per call.
- **Risk:** every retry re-executes that workflow's real tasks. For
  Doane workflows that means Salesforce upserts, Colleague writes, and
  notifications fire **again**. Retrying a workflow that already partially
  succeeded can double-apply side effects.
- **In-app safeguard:** inline LIVE warning + confirmation dialog stating the
  execution count.
- **Before you test:** retry a single known-safe execution first; confirm the
  workflow is idempotent before bulk-retrying.

### C3. Migration batch "Retry Failures"
- **Where:** Migrations tab → batch card → Retry Failures.
  `app/routes/batches.py` `retry_failures`.
- **What happens:** paginates through **every** FAILED execution in the batch
  and retries each one. Unlike C2 there is **no 500 cap** — a large batch
  retries everything.
- **Risk:** same re-triggered side effects as C2, at unbounded scale.
- **In-app safeguard:** inline LIVE warning + confirmation dialog.
- **Before you test:** use a batch with a small, known failure set; check the
  batch status first so you know the count you are about to retry.

---

## HIGH — real side effects

### H1. Workflow Test Harness — live run
- **Where:** JQ Lab tab → Test Harness sub-tab → Run Test.
  `app/routes/test_harness.py` `run_test`.
- **What happens:** in mock mode the run is simulated in-process and is
  side-effect free. In **live mode** it POSTs to Conductor's `/api/workflow/test`
  endpoint.
- **Risk:** Conductor's test endpoint only mocks the task references you supply
  in `task_mocks`. **Any task reference left without a mock falls through to a
  real worker** — which can perform real upserts/writes.
- **In-app safeguard:** inline LIVE warning on the Test Configuration card.
- **Before you test:** supply a mock for **every** task reference in the
  workflow (use "Load Task Refs" to enumerate them) before running live.

### H2. Daily digest notifications (scheduled)
- **Where:** `app/routes/digest.py` `init_scheduler`,
  `app/notification_provider.py` `deliver_digest`.
- **What happens:** APScheduler runs `generate_daily_digest` at **06:00 UTC
  daily** and then delivers it. If `SMTP_*` / `DIGEST_EMAIL_TO` or
  `GCHAT_WEBHOOK_URL` are configured, it sends a **real email and/or Google
  Chat message**.
- **Risk:** a production-pointed instance left running overnight sends a digest
  to real recipients — possibly with confusing/duplicate content while testing.
- **In-app safeguard:** none (background job, no UI surface).
- **Before you test:** leave `SMTP_*`, `DIGEST_EMAIL_TO`, and
  `GCHAT_WEBHOOK_URL` **unset** in the environment you test from. Delivery is
  skipped when a channel is not configured.

---

## MEDIUM — correctness / trust hazards

### M1. Silent mock fallback masks live failures
- **Where:** `app/conductor_client.py`, `app/sf_provider.py`,
  `app/ethos_provider.py` — every live read path is wrapped in
  `try: ... except Exception: return _mock_...()`.
- **What happens:** if a live call fails (auth error, timeout, 5xx) the client
  **silently returns fabricated fixture data** instead of surfacing the error.
- **Risk:** while testing in production you may believe you are looking at real
  data when you are actually looking at fixtures — and a real outage stays
  invisible. This is explicitly a forbidden pattern under the Mock/Live Signal
  standard.
- **In-app safeguard:** the navbar chip / `mock` flag reflect **configuration**
  (is `CONDUCTOR_URL` set), **not** whether the last call actually succeeded —
  so they do **not** catch this case.
- **Before you test:** cross-check with `GET /api/v1/health/deep` →
  `checks.conductor`; if it reports an error while the UI still shows data, the
  data is fabricated. Recommended fix: make the live path surface the error
  instead of falling back silently.

### M2. SOQL built by string interpolation
- **Where:** `app/sf_provider.py` — `find_person_by_sis_id`,
  `find_person_by_guid`, `find_duplicate_accounts`. Used by the Salesforce
  Console and the Correlation Tracer.
- **What happens:** the lookup value is interpolated directly into the SOQL
  `WHERE` clause (`WHERE SIS_ID__c = '<value>'`).
- **Risk:** a value containing a quote breaks the query; a crafted value can
  broaden it and read more records than intended. These are read-only queries,
  but they run against **production Salesforce**.
- **In-app safeguard:** none.
- **Before you test:** only feed known-good identifiers. Recommended fix:
  parameterize / escape SOQL inputs.

---

## LOW — configuration footguns

### L1. `SECRET_KEY` default
- **Where:** `app/__init__.py` — `SECRET_KEY` defaults to
  `"dev-secret-key-change-in-prod"`.
- **Risk:** if a production deploy does not set `SECRET_KEY`, Flask sessions are
  signed with a publicly known key.
- **Before you test:** set a real `SECRET_KEY` in any production-facing
  environment.

### L2. `DATABASE_URL` pointed at a production database
- **Where:** `app/__init__.py` — `db.create_all()` runs on startup against
  whatever `DATABASE_URL` points to.
- **What happens:** `create_all()` is additive (it never drops tables), but it
  will issue `CREATE TABLE` DDL against the target database.
- **Risk:** the companion's own tables (`migration_batch`, `saved_search`,
  `jq_expression`, `test_preset`) would be created in an unintended database.
- **Before you test:** point `DATABASE_URL` at the companion's own database,
  not a shared production DB.

### L3. Salesforce service-account auth
- **Where:** `app/sf_provider.py` `_get_access_token` — OAuth2
  username/password flow as `conductor-svc@doane.edu`.
- **Risk:** repeated failed logins (bad `SF_PASSWORD` / `SF_SECURITY_TOKEN`)
  can lock the shared service account.
- **Before you test:** verify credentials with a single call (`GET
  /api/v1/sf/health`) before exercising Salesforce-backed features.

---

## Safer production-testing checklist

1. Confirm the navbar shows the green **LIVE** chip and the banner is visible —
   you know you are no longer on fixtures.
2. Leave digest delivery disabled: `SMTP_*`, `DIGEST_EMAIL_TO`,
   `GCHAT_WEBHOOK_URL` unset (H2).
3. Point `DATABASE_URL` at the companion's own DB, not a production DB (L2).
4. Set a real `SECRET_KEY` (L1).
5. Read-only surfaces first — Search, Workers, Diff, Digest view, Traces — to
   confirm connectivity before touching any write surface.
6. For any CRITICAL action, test against a single known-safe record before
   doing anything in bulk.
7. If the UI shows data but `/api/v1/health/deep` reports a Conductor error,
   stop — you are looking at silent mock fallback (M1).
