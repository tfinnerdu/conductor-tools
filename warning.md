# ⚠ Production Testing — Caustic Operations

This document flags every spot in Conductor Companion that can have a
**detrimental effect on a real environment**. It exists because testing is
moving to production: the local instance has little data and there is no
dedicated dev/staging Conductor.

Read this before exercising any write/action surface against a live Conductor,
Salesforce, or Colleague.

---

## Mock data is opt-in via SHOW_MOCK

By default the app makes real calls to Conductor, Salesforce, and Ethos. If an
upstream call fails, the affected tab shows an **error** — there is no silent
fallback to fixture data. A standing banner at the top of every page reminds
you that the console acts on a real Conductor, and every destructive surface
carries an inline **⚠** warning callout.

Mock mode is a single, explicit, all-or-nothing toggle:

| Setting | Behavior |
|---|---|
| `SHOW_MOCK` unset (default) | Every integration makes real calls. Errors propagate. MOCK chip hidden. Production-safety banner and inline warnings visible. |
| `SHOW_MOCK=1` / `true` / `yes` | **Every** integration returns fixture data (no per-integration override). Amber **MOCK** chip appears in the navbar. `X-Mock-Mode: true` header on API responses. Health endpoint reports `"mock": true`. Production-safety banner and inline warnings hidden — the actions are simulations. |

Every state-changing action — in either mode — raises a **confirmation
dialog** that names the action and its impact before it runs. Confirms stay on
in mock mode so the flow is exercised end-to-end.

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

### H1. Workflow Test Harness — Run Test
- **Where:** JQ Lab tab → Test Harness sub-tab → Run Test.
  `app/routes/test_harness.py` `run_test`.
- **What happens:** every run POSTs to Conductor's `/api/workflow/test`
  endpoint on the live Conductor.
- **Risk:** Conductor's test endpoint only mocks the task references you supply
  in `task_mocks`. **Any task reference left without a mock falls through to a
  real worker** — which can perform real upserts/writes.
- **In-app safeguard:** inline warning on the Test Configuration card +
  confirmation dialog.
- **Before you test:** supply a mock for **every** task reference in the
  workflow (use "Load Task Refs" to enumerate them) before running it.

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

### M1. SOQL built by string interpolation
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

### M2. DOB Repair tab displays applicant PII
- **Where:** DOB Repair tab. `app/routes/dob_repair.py`, `app/dob_detector.py`.
  Detects PD0002124 (Instant Enrollment DOB timezone shift) and renders a
  review queue.
- **What happens:** the tab displays name, date of birth, mailing address,
  email, and phone for every candidate and elevated-risk record in whatever
  PERSON export is analyzed. This is display only — the tab never writes to
  Colleague, Ethos, or NAE; it only persists reviewer decisions in Conductor
  Companion's own database and exports an approved-corrections CSV for a
  separate, sanctioned apply step.
- **Risk:** unlike every other tab, the risk here is not a live mutation —
  it's exposure. Anyone with access to Conductor Companion can see applicant
  identity data for whatever export is currently loaded.
- **In-app safeguard:** none beyond whatever access control fronts Conductor
  Companion itself (this app has no per-tab auth).
- **Before you test:** restrict who can reach this tab to the actual DOB
  review team, the same way the original standalone tool's deployment guide
  recommends — do not expose it on a shared/open internal surface. Use
  synthetic or already-redacted data for anything beyond a real review pass.

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

1. Confirm `SHOW_MOCK` is **unset** and the navbar shows no MOCK chip — you
   are on real data, not fixtures.
2. Leave digest delivery disabled: `SMTP_*`, `DIGEST_EMAIL_TO`,
   `GCHAT_WEBHOOK_URL` unset (H2).
3. Point `DATABASE_URL` at the companion's own DB, not a production DB (L2).
4. Set a real `SECRET_KEY` (L1).
5. Read-only surfaces first — Search, Workers, Diff, Digest view, Traces — to
   confirm connectivity. If a tab shows an error, Conductor is unreachable;
   the app will not hide that behind fabricated data.
6. For any CRITICAL action, test against a single known-safe record before
   doing anything in bulk.
7. Read each confirmation dialog before accepting it — it names the exact
   action and its production impact.
