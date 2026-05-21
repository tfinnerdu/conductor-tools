# Conductor Companion — User Guide

Conductor Companion is a web tool built for the Doane platform team that extends the Orkes Conductor UI with workflow search, error diagnosis, performance monitoring, testing, and cross-system tracing. This guide walks through every tab and every function in the order they appear in the navigation bar.

---

## Getting Started

Open your browser and navigate to `http://localhost:5007` (or the network URL printed in the hub console when the app starts).

The orange Doane top bar shows the app name and current version number. Below it, the navy navigation bar has nine tabs. Click any tab to switch to it. The app does not reload between tabs — everything runs in the same page.

**Mock mode:** If Conductor is unreachable or `CONDUCTOR_URL` is not set, the app returns realistic demo data automatically. You can explore every feature without a live Conductor connection. A badge in the health endpoint indicates when mock mode is active.

---

## Search Tab

**What it does:** Find workflow executions using a combination of type, status, free text, and input field filters. Export results to CSV or save the search for later reuse.

### Workflow Type

The dropdown lists every workflow definition registered in Conductor. Select one to scope your search to that workflow type. Leave it blank to search across all types.

### Status

Five radio buttons filter by execution state:

| Option | Returns |
|---|---|
| All | Every execution regardless of state |
| Completed | Successfully finished executions |
| Failed | Executions that ended in failure |
| Running | Currently in-progress executions |
| Paused | Executions that have been manually paused |

### Free Text

Full-text search against Conductor's index. Useful when you know part of a correlation ID, workflow ID, input value, or any other string associated with the execution.

### Input Field Filters

Filter results by values inside the workflow's input payload. Click **+ Add Filter** to add a filter row. Each row has three fields:

- **Path** — dot-notation path to the field inside the input payload (e.g. `input.studentId`, `input.address.zip`)
- **Operator** — how to compare the field value:
  - `equals` / `not equals` — exact match
  - `contains` / `not contains` — substring match
  - `exists` — field is present in the payload (no value needed)
  - `not exists` — field is absent from the payload
- **Value** — the value to compare against (not required for exists/not_exists)

Add as many filter rows as needed. All filters are applied together (AND logic). Click the **×** on any row to remove it.

### Buttons

- **Search** — run the search with the current parameters. Results appear in the table below. A status count summary (e.g. "12 Completed, 3 Failed, 1 Running") appears above the table.
- **Export CSV** — run the same search and download the results as `workflow_search_results.csv`. Columns: Workflow ID, Type, Status, Correlation ID, Start Time, End Time, Version.
- **Save Search** — open a dialog to name the current search configuration. Saved searches appear in the panel on the right side of the tab.

### Results Table

Columns: Workflow ID, Type, Status, Correlation ID, Start Time, End Time, Version. Each row is one execution. Status badges are color-coded (green = Completed, red = Failed, blue = Running, yellow = Paused).

### Saved Searches

Saved searches are listed in the right column. Click one to instantly re-run it with its original parameters. Click the **×** button to delete a saved search. Saved searches persist across browser sessions (stored in the database).

---

## JQ Lab Tab

**What it does:** Write and test jq expressions against real Conductor task output. Save working expressions to a shared library. Generate ready-to-paste `JSON_JQ_TRANSFORM` task definitions. Run full workflow simulations in the Test Harness sub-tab.

The JQ Lab has three sub-tabs across the middle of the panel: **Sandbox**, **Library**, and **Test Harness**.

---

### Sandbox Sub-Tab

The main expression development area.

#### Input JSON

The left textarea holds the JSON data your expression will run against. You can paste JSON manually or load it directly from a Conductor execution (see Load from Execution below).

#### JQ Expression

The right textarea holds the jq expression. Standard jq syntax applies (e.g. `.data.students[] | select(.enrolled == true) | .id`).

#### Load from Execution

Pulls the output of a real task directly from Conductor instead of pasting JSON manually.

- **Workflow ID** — the execution ID of the workflow you want to inspect.
- **Task Ref** (optional) — the reference name of the specific task whose output you want. If omitted, the app uses the last completed task.

Click **Load Output**. The task's `outputData` is placed into the Input JSON textarea, ready for you to write an expression against it.

#### Evaluate

Click **Evaluate** to run the expression against the input. The result appears in the block below the buttons. If the expression has a syntax error or fails, the red error box appears with the jq error message.

#### Copy as Conductor Task

Click **Copy as Conductor Task** to wrap your expression in a complete `JSON_JQ_TRANSFORM` task definition JSON. The JSON is formatted and either copied to clipboard or displayed in a panel for you to copy manually. Paste it directly into your workflow definition in Conductor.

#### Save to Library

Click **Save to Library** to persist the current expression to the shared library. A dialog asks for:

- **Name** (required) — a short label for the expression
- **Description** — what the expression does and where it is used
- **Resource Name** — the Conductor workflow or system this expression is associated with
- **Use Case** — freeform tag for categorization
- **Tags** — comma-separated keywords for filtering

Saved expressions are visible to the whole team and survive browser sessions.

---

### Library Sub-Tab

Lists all saved expressions, ordered by use count (most-used first).

Each entry shows the expression name, description, resource name, use count, and the expression itself. Click **Load** to open an expression in the Sandbox. The use count increments each time an expression is loaded.

Filter the list by **Tag** or **Resource Name** using the inputs at the top of the panel.

---

### Test Harness Sub-Tab

**What it does:** Run a full workflow simulation using mock task outputs, without needing a live Conductor execution. Useful for verifying that a workflow produces the right output for a given input, and for testing error paths.

#### Test Configuration

- **Workflow** — select the workflow to test from the dropdown (populated from Conductor or mock).
- **Version** — optional. If blank, the latest version is used.
- **Workflow Input JSON** — the input payload to pass to the workflow, as a JSON object.
- **Task Mocks JSON** — define what each task should return when simulated. Format:

```json
{
  "task_ref_name": {
    "outputData": {
      "key": "value"
    }
  }
}
```

Any task not listed in Task Mocks will complete with empty output. Any task whose outputData includes `"status": "FAILED"` will cause a simulated task failure.

#### Load Task Refs

After selecting a workflow, click **Load Task Refs** to see a list of every task reference name in the workflow definition. Click **Add Mock** next to any task to insert an empty mock entry into the Task Mocks textarea, pre-filled with the correct reference name.

#### Run Test

Click **Run Test**. The app simulates the workflow execution in-process (mock mode) or against a live Conductor (if configured and not in mock mode). The **Test Result** card appears with:

- Overall execution status (COMPLETED or FAILED)
- A table of each task with its reference name, type, status, and output data
- The final workflow output JSON

#### Presets

Four built-in presets represent common Doane integration scenarios:

| Preset | Workflow | Scenario |
|---|---|---|
| Person created in Colleague | `student_enrollment` | New person flowing through enrollment with a full Ethos person payload |
| Person address updated | `student_enrollment` | Address-change event with the updated address in mock output |
| Application submitted | `financial_aid_processing` | Admissions application with payment charged |
| Ethos 404 error | `student_enrollment` | `ethos_get_person` cannot find the record — shows a FAILED result |

Click **Apply** next to any preset to load its configuration into the form. Then click **Run Test**.

#### Save as Preset

After configuring a test you want to reuse, click **Save as Preset** and give it a name. It appears in the Presets list for all future sessions (stored in the database).

---

## Workers Tab

**What it does:** Show the real-time health and performance of every task worker registered with Conductor. Refreshes automatically every 5 seconds.

### Worker Registry Table

Each row is one task type. Columns:

| Column | Description |
|---|---|
| Task Type | The task name workers are polling for |
| Workers | Number of distinct worker IDs that have polled recently |
| Last Poll | How long ago the most recent poll happened (e.g. "2s", "45s") |
| Queue Depth | Number of tasks waiting in the queue right now |
| Status | Color-coded health classification (see below) |

**Health classification:**

| Status | Meaning | Threshold |
|---|---|---|
| 🟢 healthy | Polling normally | Last poll < 5 seconds ago |
| 🟡 slow_poll | Workers may be busy or under load | Last poll 5–30 seconds ago |
| 🔴 down | Worker is likely offline | Last poll > 30 seconds ago |
| 🔴 no_workers | No worker IDs registered for this task type at all | — |

Rows are sorted so the most problematic statuses appear at the top.

### Performance Stats

Click any row to expand a performance panel below the table. It shows:

- Total executions tracked
- Completed count and success rate (%)
- Failed count
- Average duration (ms)
- Minimum and maximum duration
- p50, p95, and p99 duration percentiles

Click the row again to collapse the panel.

### Refresh Counter

The "Last refreshed: Xs ago" label counts up from zero and resets on each automatic refresh. If it climbs past 10 seconds, the auto-refresh cycle may have stalled — try reloading the page.

### Refresh Now

Click **Refresh Now** to force an immediate update without waiting for the next automatic cycle.

---

## Migrations Tab

**What it does:** Track and manage large batch operations where many workflow executions are kicked off under a shared correlation ID prefix. Monitor progress, retry failures, and export error lists.

### Migration Batch List

The left column lists all batches sorted by creation date (newest first). Each card shows the batch name, workflow type, creation date, and the last-known status summary if the batch has been refreshed.

Click a batch card to select it and reveal the action buttons (Refresh, Retry Failures, Export CSV).

### Creating a Batch

Fill in the **New Batch** form on the right side:

- **Batch Name** (required) — a human-readable label for this migration run (e.g. "Q1 2025 Student Enrollment").
- **Workflow Name** (required) — the workflow type all executions in this batch use.
- **Correlation ID Prefix** — the prefix shared by all correlation IDs in this batch (e.g. `migration-q1-2025-`). Leave blank if you are not filtering by correlation ID.
- **Expected Count** — total number of executions you expect. Used to calculate the progress percentage on the status card.

Click **Create Batch**. The new batch appears at the top of the left column.

### Checking Status

Select a batch and click **Refresh**. The tool pages through all Conductor search results for that workflow type and correlation prefix and shows:

- A progress bar (completed + failed / expected)
- Status counts: Completed, Failed, Running, Paused
- Timestamp of the last refresh

### Retrying Failures

Select a batch and click **Retry Failures**. After confirmation, the tool finds every FAILED execution in the batch and calls Conductor's retry endpoint for each one. A toast message reports how many were successfully retried and how many errors occurred.

### Exporting Failures to CSV

Select a batch and click **Export CSV** to download a spreadsheet of every FAILED execution in the batch. Columns: Workflow ID, Status, Correlation ID, Start Time, End Time, Version. Useful for handing off to an operations team or for audit records.

---

## Diff Tab

**What it does:** Compare two versions of a workflow definition side by side, visualize what changed, and determine which workflows would be affected by changes to a shared task type.

### Version Comparison

1. Select a **Workflow** from the dropdown. Version A and Version B dropdowns populate automatically with the available versions.
2. Choose **Version A** and **Version B** — the two versions you want to compare. Typically A is the older version and B is the newer one, but the order is flexible.
3. Select a **Diff Mode**:
   - **Full JSON** — compares the complete workflow definition JSON. Shows all differences including metadata, timeout settings, etc.
   - **Tasks Only** — compares only the `tasks` array. Usually the most relevant mode for day-to-day changes.
   - **Significant Changes** — filters the diff to show only lines where a task name, type, reference name, or input parameters changed. Omits whitespace and formatting noise.
4. Click **Compare**.

The diff renders below with color-coded lines:
- **Green** — lines added in Version B
- **Red** — lines removed from Version A
- **Blue** — section headers from the diff output
- **Gray** — unchanged context lines

A summary above the diff shows the total count of additions and removals.

### Dependency Map

Click **Load Dependency Map** to fetch a table of every workflow version and the task types it references. This gives a full picture of which workflows depend on which tasks. The table is searchable and sortable. Useful before making changes to a shared task type.

### Impact Analysis

If you are planning to modify a task type (rename it, change its input parameters, etc.), use Impact Analysis to find every workflow version that will be affected.

Enter the **Task Type** name in the input field and click **Analyze Impact**. The result lists each affected workflow with its version number and the specific task reference names used within that workflow. Use this list to plan which workflow definitions need to be updated alongside the task change.

---

## Reconciler Tab

**What it does:** Group failed workflow executions by the task type that caused the failure, identify the most common error codes, and retry failures in bulk.

### Failure Summary

When you open the tab, the app loads a summary of all failures in the configured time window. The summary section shows:

- Total failure count across all workflows in the window
- A breakdown by workflow name → task type → error code (e.g. `HTTP_404 x7`, `TIMEOUT x2`, `DUPLICATE_VALUE x1`)

**Hours back dropdown:** Change the look-back window. Options: 6h, 24h (default), 48h, 72h. The summary reloads automatically when you change the window.

### Failures by Task Type Table

Below the summary, a paginated table shows individual failure groups. Each row represents one task type that caused failures, with columns:

- Task Type
- Failure Count
- Most Common Error Code
- Workflow Name
- Actions (Retry All, checkbox for bulk select)

Click **Retry All** next to any row to retry every execution in that group immediately. A toast confirms how many were retried.

Use pagination controls to move between pages of results.

### Bulk Retry

Check one or more rows using the checkboxes on the left. A **Bulk Retry Selected** button appears at the bottom. Click it to retry all selected executions in a single API call. Maximum 500 executions per bulk retry call. The result reports how many were successfully retried and how many returned errors.

### Failure Detail

Click any row in the table to expand detail for that failure group, or call the API directly:

```
GET /api/v1/reconciler/failures/<workflow_id>
```

Detail includes:
- The failed task type and reference name
- The exact failure reason from Conductor
- An extracted error code (e.g. `HTTP_404`, `TIMEOUT`, `DUPLICATE_VALUE`, `UNKNOWN_ERROR`)
- The retry count for this execution
- The workflow input payload (with `sisId` highlighted if present)

### Reconciler Summary

The `/api/v1/reconciler/summary` endpoint (available for direct API access) returns a hierarchical breakdown of all failures across all workflows, grouped by workflow → task type → error code. Useful for building dashboards or automated alerting.

---

## Traces Tab

**What it does:** Follow a person's data through Conductor, Salesforce, and Ethos by searching with a Doane GUID or SIS_ID. A timeline shows every system event associated with that person in chronological order.

### Tracing a Person

1. Select the identifier type using the radio buttons: **GUID** (a UUID-format Ethos GUID) or **SIS_ID** (the Colleague/Banner SIS identifier).
2. Type the identifier in the text field.
3. Click **Trace**.

The app searches three systems simultaneously:
- **Conductor** — any workflow execution that references the identifier in its input, correlation ID, or output
- **Salesforce** — PersonAccount records matching the GUID or SIS_ID
- **Ethos** — recent change notification events from the in-memory buffer

### Diagnosis Message

Directly below the search form, a colored diagnosis message summarizes what was found in Salesforce:

| Color | Meaning |
|---|---|
| 🟢 Green | Record found, SIS_ID__c is populated, data looks healthy |
| 🟡 Yellow | Record found but has a warning (e.g. SIS_ID__c is missing or blank) |
| 🔴 Red | No record found, or more than one record found (duplicate) |

### Event Timeline

The timeline lists all events sorted by timestamp, oldest first. Each event shows:

- **System badge** — CONDUCTOR (navy), SALESFORCE (blue), or ETHOS (teal)
- **Status icon** — ✓ (ok), ✗ (error), ⚠ (warning)
- **Event name** — a short label describing what happened (e.g. "Workflow started", "PersonAccount found", "Ethos person.create")
- **Detail** — additional context (workflow ID, record ID, error message, etc.)

Conductor events include: workflow start, workflow end (completed or failed), and individual task failures when present.

Salesforce events include the record lookup result — records found, ID, name, and SIS_ID__c value.

Ethos events include any recent change notifications in the buffer that match the identifier (matched against both GUID and SIS_ID fields in the event payload).

### Counts Summary

Above the timeline, a summary line shows the total number of Conductor executions found, the Salesforce record count, and whether any Ethos events matched.

### Recent Traces

The **Recent Traces** card at the bottom of the tab shows the last 20 trace searches, newest first. Each entry shows:
- The identifier searched
- When the trace ran
- How many Conductor hits were found
- Whether any errors appeared in the timeline

Click **Retrace** next to any entry to re-run that search with the current data.

---

## Digest Tab

**What it does:** Show a daily performance summary across all watched workflows. Surfaces actionable recommendations, performance trends, and regressions in one view. The digest is pre-generated automatically at 06:00 UTC each day and cached in memory.

### Recommendations

The top card lists actionable recommendations, sorted with errors first and warnings below.

**Error-level recommendations (red):**
- A workflow has a failure rate above 20%
- A worker task type has no registered pollers (`no_workers`)
- A worker task type has not polled in 30+ seconds (`down`)

**Warning-level recommendations (orange/yellow):**
- A workflow has a failure rate above 5% but below 20%
- A worker task type's last poll was 5–30 seconds ago (`slow_poll`)
- A workflow is more than 50% slower than its 7-day average (regression)

If no issues are detected, a green "No issues found" message is shown instead.

Click **Refresh** to regenerate the recommendations on demand.

### Workflow Performance Table

Each row is one workflow type. Columns:

| Column | Description |
|---|---|
| Workflow | Workflow name |
| Total | Total executions in the digest period |
| Failed | Count of FAILED executions |
| Failure % | Failure rate — highlighted orange above 5%, red above 20% |
| Avg ms | Average execution duration in milliseconds |
| Trend | Performance trend vs. the 7-day historical average |

**Trend values:**
- ↑ **up** — current average is more than 15% slower than the 7-day average
- ↓ **down** — current average is more than 15% faster than the 7-day average
- → **stable** — within 15% of the 7-day average
- ★ **new** — no historical data available (workflow has not appeared in previous digests)

### Regressions

If any workflow is more than 50% slower than its 7-day average, it appears in a red **Performance Regressions** card at the bottom. Each regression shows:
- Workflow name
- Current average duration
- 7-day historical average
- Percentage slower

### Workflow History

The 7-day history for any individual workflow is available via the API:

```
GET /api/v1/digest/workflow/<name>/history
```

Returns the last 7 days of daily stats (total, failed, avg_ms) for that workflow, one entry per day. Days with no cached digest show zeros.

### Digest Schedule

The digest is regenerated automatically at **06:00 UTC daily** by a background APScheduler job. If a digest notification channel is configured (email or GChat), the digest is also delivered to those channels at that time.

To trigger an immediate regeneration, click **Refresh** or call `GET /api/v1/digest/daily` directly.

---

## Settings Tab

**What it does:** Manage Conductor secrets — the named key-value pairs that workflows reference at runtime using the `${secret.NAME}` syntax.

### What Are Conductor Secrets?

Secrets are named credentials stored securely in Conductor. Workflow task definitions reference them as `${secret.PAYMENT_API_KEY}` rather than hardcoding the value. This means rotating a credential only requires updating it once in the Secrets tab rather than editing every workflow definition.

### Secrets List

The table lists every secret name currently stored in Conductor. Columns:
- **Secret Name** — the key used in workflow definitions
- **Used In** — number of workflow definitions that reference this secret
- **Actions** — Delete button

Click on a secret name to see which workflow definitions and which specific tasks reference it. The usage lookup searches all workflow task `inputParameters` for `${secret.NAME}` and `__secret.NAME` patterns.

### Adding or Updating a Secret

Fill in the form at the top of the card:

- **Secret Name** — the key name (e.g. `PAYMENT_API_KEY`). Must not contain spaces. If a secret with this name already exists, its value will be overwritten.
- **Secret Value** — the credential value. Displayed as a password field.

Click **Add / Update**. The secrets list refreshes automatically. The value is never displayed again after it is set.

### Deleting a Secret

Click the **Delete** button next to any secret in the list. Confirm when prompted. This immediately removes the secret from Conductor. Any workflow task that references it will fail at runtime until the secret is re-added.

> **Before deleting:** click the secret name to check usage. If any active workflow references it, coordinate the deletion with the team.

---

## Integrations Reference

These integrations run in the background and surface their data through the tabs above. They do not have dedicated tabs but are configured via `.env`.

### Conductor

The core integration. All workflow data, task definitions, secrets, and worker health come from Conductor. Set `CONDUCTOR_URL` in `.env`. If `CONDUCTOR_API_KEY` is set, it is sent as the `X-Authorization` header on every request. If Conductor is unreachable, the app automatically returns mock data so the UI remains functional.

### Salesforce

Used by the **Traces** tab to look up PersonAccount records by GUID or SIS_ID. Configured with Connected App credentials in `.env`:

```
SF_USERNAME=conductor-svc@doane.edu
SF_PASSWORD=
SF_SECURITY_TOKEN=
SF_CLIENT_ID=
SF_CLIENT_SECRET=
```

The app fetches an OAuth2 access token on first use and caches it for 90 minutes. The instance URL is derived from the login response and does not need to be set separately unless you need to target a sandbox.

If Salesforce credentials are not configured, Salesforce lookups return realistic mock data and the health endpoint reports `not_configured`.

### Ethos (Ellucian)

Used by the **Traces** tab to show recent change notification events. Configured with:

```
ETHOS_URL=
ETHOS_API_KEY=
```

Ethos events are held in an in-memory ring buffer and matched against person identifiers during a trace. Events can also be ingested directly via `POST /api/v1/ethos/events`.

If Ethos credentials are not configured, the Traces timeline simply omits the ETHOS section and the health endpoint reports `not_configured`.

### Digest Notifications

The daily digest can be delivered automatically at 06:00 UTC via email and/or Google Chat:

**Email:**
```
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
DIGEST_EMAIL_FROM=conductor-companion@doane.edu
DIGEST_EMAIL_TO=team@doane.edu,manager@doane.edu
```

**Google Chat:**
```
GCHAT_WEBHOOK_URL=
```

Both channels are opt-in. Configure neither, one, or both. Delivery failures are logged but never crash the scheduler.

---

## Health Endpoints

Two health endpoints are available for monitoring and CI:

| Endpoint | Use |
|---|---|
| `GET /health` | Lightweight check safe for 30-second polling. Returns uptime, version, and a quick read-only status for each integration. |
| `GET /health/deep` | Full functional check including a real Conductor API call and a database round-trip. Use for CI gates and admin smoke tests only — not for high-frequency polling. |

Both return JSON with an `ok` boolean, a `status` string (`ok` or `degraded`), and per-integration check details.
