# Conductor Companion — User Guide

Conductor Companion is a web tool built for the Doane platform team that extends the Orkes Conductor UI with workflow search, error diagnosis, performance monitoring, testing, and cross-system tracing. This guide walks through every tab and every function in the order they appear in the navigation bar.

---

## Getting Started

Open your browser and navigate to `http://localhost:5007` (or the network URL printed in the hub console when the app starts).

The orange Doane top bar shows the app name and current version number. Below it, the navy navigation bar has nine tabs. Click any tab to switch to it. The app does not reload between tabs — everything runs in the same page.

**Connecting to Conductor:** Set `CONDUCTOR_URL` to your Conductor instance. The app has no demo or mock mode — every tab calls the real Conductor. See the next section.

---

## Production Safety

Conductor Companion always acts on the real Conductor that `CONDUCTOR_URL` points at. There is no demo or mock mode: if Conductor is unreachable, a tab shows an error rather than fabricated data.

A standing banner across the top of every page reminds you that the console acts on a real Conductor.

**Confirmation dialogs.** Every action that changes state — saving or deleting a secret, retrying workflows, creating a batch, running a test, saving a search, expression, or preset — raises a confirmation dialog that names the action and its impact before it runs. The destructive tabs (Settings, Reconciler, Migrations, Test Harness) also show an inline **⚠** warning callout.

Before testing against production, read `warning.md` in the repository root. It lists every operation that can have a detrimental effect on a live environment and how to test it safely.

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

**What it does:** Run a workflow against Conductor's workflow test endpoint with mock task outputs you supply. Useful for verifying that a workflow produces the right output for a given input, and for testing error paths, without running real workers for the tasks you mock.

#### Test Configuration

- **Workflow** — select the workflow to test from the dropdown (populated from Conductor).
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

Click **Run Test** and confirm the dialog. The app POSTs the workflow, input, and task mocks to Conductor's workflow test endpoint. Any task reference left without a mock runs a real worker, so mock every task to keep the run side-effect free. The **Test Result** card appears with:

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
2. Choose **Version A** and **Version B** — the two versions you want to compare.
3. Select a **Diff Mode**:
   - **Full JSON** — compares the complete workflow definition JSON.
   - **Tasks Only** — compares only the `tasks` array.
   - **Significant Changes** — filters to only lines where a task name, type, reference name, or input parameters changed.
4. Click **Compare**.

The diff renders below with color-coded lines:
- **Green** — lines added in Version B
- **Red** — lines removed from Version A
- **Blue** — section headers
- **Gray** — unchanged context lines

### Dependency Map

Click **Load Dependency Map** to fetch a table of every workflow version and the task types it references. Useful before making changes to a shared task type.

### Impact Analysis

Enter the **Task Type** name and click **Analyze Impact**. The result lists each affected workflow with its version number and the specific task reference names used within that workflow.

---

## Reconciler Tab

**What it does:** Group failed workflow executions by the task type that caused the failure, identify the most common error codes, and retry failures in bulk.

### Failure Summary

Loads a summary of all failures in the configured time window grouped by workflow → task type → error code (e.g. `HTTP_404 x7`, `TIMEOUT x2`).

**Hours back dropdown:** Options: 6h, 24h (default), 48h, 72h. The summary reloads when you change the window.

### Failures by Task Type Table

Paginated table of individual failure groups. Click **Retry All** next to any row to retry every execution in that group immediately.

### Bulk Retry

Check one or more rows using the checkboxes. A **Bulk Retry Selected** button appears at the bottom. Maximum 500 executions per bulk retry call. The result reports how many were successfully retried and how many returned errors.

### Failure Detail

Click any row to expand detail, or call directly:

```
GET /api/v1/reconciler/failures/<workflow_id>
```

Detail includes: failed task type, exact failure reason, extracted error code (e.g. `HTTP_404`, `TIMEOUT`, `DUPLICATE_VALUE`), retry count, and workflow input with `sisId` highlighted if present.

---

## Traces Tab

**What it does:** Follow a person's data through Conductor, Salesforce, and Ethos by searching with a Doane GUID or SIS_ID.

### Tracing a Person

1. Select the identifier type: **GUID** (UUID-format Ethos GUID) or **SIS_ID** (Colleague/Banner identifier).
2. Type the identifier in the text field.
3. Click **Trace**.

The app searches three systems simultaneously: Conductor (workflow executions), Salesforce (PersonAccount records), and Ethos (recent change notification events from the in-memory buffer).

### Diagnosis Message

| Color | Meaning |
|---|---|
| 🟢 Green | Record found, SIS_ID__c populated, data looks healthy |
| 🟡 Yellow | Record found but has a warning (e.g. SIS_ID__c missing) |
| 🔴 Red | No record found, or duplicate records detected |

### Event Timeline

Events sorted by timestamp, oldest first. Each event shows:
- **System badge** — CONDUCTOR (navy), SALESFORCE (blue), ETHOS (teal)
- **Status icon** — ✓ ok, ✗ error, ⚠ warning
- **Event name** and **detail** string

### Recent Traces

The last 20 trace searches. Click **Retrace** to re-run any previous search with current data.

---

## Digest Tab

**What it does:** Daily performance summary across all watched workflows with recommendations, trends, and regression detection.

### Recommendations

**Error-level (red):** failure rate > 20%, workers down or no_workers.
**Warning-level (orange):** failure rate 5–20%, slow_poll workers, performance regressions.

Click **Refresh** to regenerate on demand. Auto-generated at **06:00 UTC daily**.

### Workflow Performance Table

| Column | Description |
|---|---|
| Workflow | Workflow name |
| Total | Executions in the digest period |
| Failed | Count of FAILED executions |
| Failure % | Rate — orange > 5%, red > 20% |
| Avg ms | Average execution duration |
| Trend | ↑ up (>15% slower), ↓ down (>15% faster), → stable, ★ new |

### Regressions

Workflows more than 50% slower than their 7-day average appear in a red Regressions card with current avg, historical avg, and % slower.

### Workflow History

```
GET /api/v1/digest/workflow/<name>/history
```

Returns the last 7 days of daily stats (total, failed, avg_ms) for a single workflow.

---

## Settings Tab

**What it does:** Manage Conductor secrets — named credentials that workflows reference at runtime as `${secret.NAME}`.

### Secrets List

Lists every secret name in Conductor with a usage count and Delete button. Click a secret name to see which workflow definitions and task `inputParameters` reference it.

### Adding or Updating a Secret

- **Secret Name** — the key name (e.g. `PAYMENT_API_KEY`). If it already exists, its value is overwritten.
- **Secret Value** — displayed as a password field. Never shown again after saving.

Click **Add / Update**. A confirmation dialog appears first — saving a secret writes straight to the production Conductor secret store.

### Deleting a Secret

Click **Delete** next to any secret. Check usage first — any active workflow referencing the secret will fail at runtime until it is re-added. A confirmation dialog spells out this impact before the secret is removed.

---

## Integrations Reference

### Conductor

Set `CONDUCTOR_URL` in `.env`. If `CONDUCTOR_API_KEY` is set, it is sent as `X-Authorization` on every request. There is no mock fallback — if Conductor is unreachable, requests surface an error.

### Salesforce

Configured with Connected App credentials:

```
SF_USERNAME=conductor-svc@doane.edu
SF_PASSWORD=
SF_SECURITY_TOKEN=
SF_CLIENT_ID=
SF_CLIENT_SECRET=
```

The app fetches an OAuth2 access token on first use and caches it for 90 minutes. `SF_INSTANCE_URL` is derived from the login response automatically — only set it to target a sandbox.

### Ethos

```
ETHOS_URL=
ETHOS_API_KEY=
```

Ethos events are held in an in-memory buffer and matched against person identifiers during a trace.

### Digest Notifications

```
# Email
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
DIGEST_EMAIL_FROM=conductor-companion@doane.edu
DIGEST_EMAIL_TO=team@doane.edu

# Google Chat
GCHAT_WEBHOOK_URL=
```

Both channels are opt-in. Delivery failures are logged but never crash the scheduler.

---

## Health Endpoints

| Endpoint | Use |
|---|---|
| `GET /health` | Lightweight — safe for 30-second polling. Returns uptime, version, integration statuses. |
| `GET /health/deep` | Functional — real Conductor API call + DB round-trip. Use for CI gates only, not high-frequency polling. |
