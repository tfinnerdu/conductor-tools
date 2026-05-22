# Conductor Companion — End-to-End Test Walkthrough

Organized by feature surface. For each feature, follow the manual steps and verify the expected outcomes.

---

## Prerequisites

- App running locally: `python -u run.py`
- App reachable at `http://localhost:5000`
- Optional: A live Conductor instance at the URL in `.env`. Without one, mock data is returned automatically.

---

## 1. Health Check

Two endpoints exist. Wire only the live-safe one to Pingdom / Uptime Kuma.

### 1a. Live-safe health check (safe for 30s polling)

**Goal:** Verify the service is alive and Conductor is reachable.

**Steps:**

1. Open a terminal and run:
   ```
   curl.exe -s http://localhost:5000/health
   ```

**Expected outcome (no live Conductor configured):**

```json
{
  "status": "ok",
  "service": "conductor-companion",
  "version": "1.2.0",
  "uptime_seconds": 4.2,
  "checks": {
    "conductor": { "ok": true, "detail": "not_configured", "latency_ms": null }
  }
}
```

**Expected outcome (live Conductor configured and reachable):**

```json
{
  "status": "ok",
  "checks": {
    "conductor": { "ok": true, "detail": "reachable", "latency_ms": 18 }
  }
}
```

**Expected outcome (Conductor unreachable):**

- HTTP 503 returned.
- `"status": "degraded"`.
- `"conductor": { "ok": false, "detail": "timeout" }`.

### 1b. Functional / deep health check (CI gates and admin diagnostics only)

**Goal:** Verify database connectivity and a real Conductor API round-trip.

**Steps:**

1. Run:
   ```
   curl.exe -s http://localhost:5000/health/deep
   ```

**Expected outcome:**

```json
{
  "status": "ok",
  "checks": {
    "db": { "ok": true, "latency_ms": 3, "detail": "connected" },
    "conductor": { "ok": true, "detail": "mock_mode", "latency_ms": null }
  },
  "request_id": "..."
}
```

- `db.ok` confirms a live database `SELECT 1` round-trip succeeded.
- `conductor.detail` is `"mock_mode"` when no `CONDUCTOR_URL` is set, or `"reachable"` with a live instance.
- Returns HTTP 503 with `"status": "degraded"` if either check fails.
- **Do not wire this endpoint to Pingdom or any automated monitor.**

---

## 2. Advanced Search

### 2a. Basic search

**Steps:**

1. Open `http://localhost:5000` in a browser.
2. The Search tab is active by default.
3. Leave all fields at defaults and click **Search**.

**Expected outcome:** A table of workflow executions appears. The status summary above shows counts like `COMPLETED: 18  FAILED: 7`.

### 2b. Filter by status

**Steps:**

1. Select **Failed** in the Status radio buttons.
2. Click **Search**.

**Expected outcome:** Only FAILED executions appear in the results table.

### 2c. Input field filter

**Steps:**

1. Click **+ Add Filter**.
2. Set path = `input.orderId`, operator = `equals`, value = `1001`.
3. Click **Search**.

**Expected outcome:** Only executions where `input.orderId` equals `1001` appear.

### 2d. Save a search

**Steps:**

1. Set Workflow Type = `order_fulfillment`, Status = `Failed`.
2. Click **Save Search**.
3. Enter a name when prompted (e.g., "Failed Orders").
4. The saved search appears in the **Saved Searches** panel.

**Expected outcome:** The saved search is listed. Click it and the search runs automatically with those parameters.

### 2e. Delete a saved search

**Steps:**

1. Click the **X** button next to a saved search.

**Expected outcome:** The search disappears from the list.

### 2f. CSV export

**Steps:**

1. Run any search that returns results.
2. Click **Export CSV**.

**Expected outcome:** A CSV file named `workflow_search_results.csv` downloads. Open it and verify it has headers `workflowId,workflowType,status,...` and one row per result.

---

## 3. JQ Lab

### 3a. Evaluate a basic expression

**Steps:**

1. Click the **JQ Lab** tab.
2. In the **Input JSON** textarea, paste:
   ```json
   {"items": [1, 2, 3, 4, 5], "name": "test"}
   ```
3. In the **JQ Expression** textarea, type: `.items | length`
4. Click **Evaluate**.

**Expected outcome:** The Result panel shows `5`. No error message appears.

### 3b. Invalid expression shows error

**Steps:**

1. In the Expression textarea, type: `!!!invalid`
2. Click **Evaluate**.

**Expected outcome:** An error message appears in the red error box below the buttons. The Result panel remains empty.

### 3c. Load from execution

**Steps:**

1. Enter a workflow execution ID in the **Workflow execution ID** field (use `mock-wf-0001` or any real ID from Search results).
2. Optionally enter a task reference name.
3. Click **Load Output**.

**Expected outcome:** The Input JSON textarea is populated with the task's output data. A success toast appears saying "Loaded output from [task type]".

### 3d. Save to library

**Steps:**

1. Enter an expression: `.results | map(.correlationId)`
2. Click **Save to Library**.
3. Enter a name and optional description.

**Expected outcome:** The expression appears in the **Expression Library** panel below. A success toast appears.

### 3e. Copy as Conductor Task JSON

**Steps:**

1. Enter an expression: `.output.result // null`
2. Click **Copy as Conductor Task**.

**Expected outcome:** A toast says "Copied to clipboard". Paste into a text editor and verify the result is a valid JSON_JQ_TRANSFORM task definition.

### 3f. Open expression from library

**Steps:**

1. In the Expression Library, find any expression.
2. Click **Open in Lab**.

**Expected outcome:** The expression is populated in the JQ Expression textarea. A toast says "Expression loaded into lab".

---

## 4. Workers

### 4a. Health board loads

**Steps:**

1. Click the **Workers** tab.

**Expected outcome:** Within a few seconds, the worker registry table populates. Each row shows a task type, worker count, last poll time, queue depth, and a color-coded status badge.

### 4b. Status classifications

**Expected outcome:**
- Workers polled within 5 seconds show a green `healthy` badge.
- Workers polled 5–30 seconds ago show a yellow `slow_poll` badge.
- Workers polled 30+ seconds ago show a red `down` badge.
- Task types with no worker records show a red `no_workers` badge.

### 4c. Auto-refresh

**Steps:**

1. Stay on the Workers tab for 10 seconds.

**Expected outcome:** The "Last refreshed: Xs ago" counter increments each second and resets to ~0 every 5 seconds when the table refreshes.

### 4d. Performance drill-down

**Steps:**

1. Click any row in the worker table.

**Expected outcome:** A performance panel appears below showing stat boxes for total executions, success rate, and failure count. A metrics table shows avg/min/max/p50/p95/p99 durations.

### 4e. Auto-refresh stops on tab switch

**Steps:**

1. Switch to another tab (e.g., Search).

**Expected outcome:** Network requests for `/api/v1/workers/status` stop. Switch back to Workers and they resume.

---

## 5. Migrations

### 5a. Create a batch

**Steps:**

1. Click the **Migrations** tab.
2. Fill in the **New Batch** form:
   - Name: `Test Migration Batch`
   - Workflow Name: select `order_fulfillment`
   - Correlation ID Prefix: `test-batch-`
   - Expected Count: `50`
3. Click **Create Batch**.

**Expected outcome:** A success toast appears. The batch appears in the **Migration Batches** panel on the left.

### 5b. Poll batch status

**Steps:**

1. Click **Refresh** on the new batch card.

**Expected outcome:** A progress bar appears showing completed/total. Status counts are displayed for COMPLETED, FAILED, and RUNNING.

### 5c. Retry failures

**Steps:**

1. On a batch card, click **Retry Failures**.
2. Confirm the dialog.

**Expected outcome:** A toast shows how many workflows were retried (e.g., "Retried 3 workflows"). The progress bar refreshes.

### 5d. Export failures CSV

**Steps:**

1. On any batch card, click **Export CSV**.

**Expected outcome:** A CSV file named `batch_[id]_[name]_failures.csv` downloads with all FAILED executions in that batch.

---

## 6. Diff

### 6a. Compare workflow versions

**Steps:**

1. Click the **Diff** tab.
2. Select `order_fulfillment` from the Workflow dropdown.
3. Version A = 1, Version B = 2 should auto-select.
4. Leave mode as **Full JSON**.
5. Click **Compare**.

**Expected outcome:** A side-by-side diff appears. Lines starting with `+` are green (additions), lines with `-` are red (removals). A summary shows added/removed line counts.

### 6b. Tasks-only mode

**Steps:**

1. Select the **Tasks Only** radio button.
2. Click **Compare**.

**Expected outcome:** The diff shows only the tasks array, making the view more focused.

### 6c. Significant changes mode

**Steps:**

1. Select the **Significant Changes** radio button.
2. Click **Compare**.

**Expected outcome:** Only lines touching task name, type, taskReferenceName, or inputParameters appear.

### 6d. No differences

**Steps:**

1. Set Version A and Version B to the same version (e.g., both 1).
2. Click **Compare**.

**Expected outcome:** A message says "No differences found between v1 and v1."

### 6e. Dependency map

**Steps:**

1. Click **Load Dependency Map**.

**Expected outcome:** A table appears listing each workflow version and the task types it uses. The task type names are shown as navy badges.

### 6f. Impact analysis

**Steps:**

1. In the **Impact Analysis** panel, enter `validate_order` in the task type field.
2. Click **Analyze Impact**.

**Expected outcome:** A table shows which workflow versions reference `validate_order` and which task reference names they use.

### 6g. Unknown task type

**Steps:**

1. Enter `nonexistent_task_xyz` in the impact analysis field.
2. Click **Analyze Impact**.

**Expected outcome:** A message says "No workflows reference task type nonexistent_task_xyz."

---

## 7. Error Reconciler

### 7a. View failure summary

**Steps:**

1. Click the **Reconciler** tab.
2. The page loads automatically and shows the failure summary grouped by workflow and task type.

**Expected outcome:** The Failure Summary card shows a count of total failures in the last 24 hours. Each workflow section lists the task types that failed with error code breakdowns (e.g., `HTTP_404 x7`, `TIMEOUT x2`).

### 7b. Change time window

**Steps:**

1. Change the **Hours back** dropdown to `6h`.

**Expected outcome:** The summary refreshes and shows only failures from the last 6 hours. The total count typically decreases.

### 7c. Drill into a failure group

**Steps:**

1. In the Failures by Task Type table, note a row with task type `ethos_get_person`.
2. Click the **Retry All** button next to that row.

**Expected outcome:** A toast notification says "Retried N workflows". The table refreshes.

### 7d. Bulk retry with checkboxes

**Steps:**

1. Check the checkbox next to two or more failure groups.
2. The **Bulk Retry Selected** button appears at the bottom with a count of selected executions.
3. Click **Bulk Retry Selected**.

**Expected outcome:** A success message shows how many were retried. The selection is cleared.

### 7e. Drill into a single execution

**Steps:**

1. Run:
   ```
   curl.exe -s http://localhost:5000/api/v1/reconciler/failures/mock-fail-ethos-0001
   ```

**Expected outcome:** A JSON object with `failedTask`, `errorCode`, `retryCount`, and `sisId` fields. The `errorCode` should be a short code like `HTTP_404` rather than the full error string.

---

## 8. Correlation Tracer

### 8a. Trace by GUID

**Steps:**

1. Click the **Traces** tab.
2. Leave **GUID** selected in the radio buttons.
3. Enter a GUID such as `11111111-1111-1111-1111-111111111111`.
4. Click **Trace**.

**Expected outcome:** The Event Timeline card appears with events sorted by timestamp. Each event has a colored system badge (CONDUCTOR in navy, SALESFORCE in blue). A diagnosis message appears above the timeline.

### 8b. Trace by SIS_ID

**Steps:**

1. Select **SIS_ID** in the radio buttons.
2. Enter `SIS123456`.
3. Click **Trace**.

**Expected outcome:** The timeline shows Conductor search results and a Salesforce record lookup. The diagnosis says "Record looks healthy" for a normal SIS_ID.

### 8c. Trace an identifier with no records

**Steps:**

1. Select **SIS_ID** and enter `SIS_NOTFOUND`.
2. Click **Trace**.

**Expected outcome:** The Salesforce event shows a red error status. The diagnosis says "Record not found in Salesforce — migration has not run or failed."

### 8d. Trace a duplicate record

**Steps:**

1. Select **SIS_ID** and enter any value containing the word `dup` (e.g., `SIS_DUP123`).
2. Click **Trace**.

**Expected outcome:** The Salesforce event shows a yellow warning badge. The diagnosis says "DUPLICATE: 2 records found — merge required."

### 8e. Read recent traces

**Steps:**

1. After performing several traces, scroll down to the **Recent Traces** section.

**Expected outcome:** The last traces are listed with timestamps, identifiers, event counts, and ok/error badges. Clicking **Retrace** on any entry re-runs that trace automatically.

### 8f. GET shorthand

**Steps:**

1. Run:
   ```
   curl.exe -s http://localhost:5000/api/v1/tracer/person/SIS123456
   ```

**Expected outcome:** Same response shape as the POST endpoint. UUID-format identifiers are auto-detected as GUIDs; all others are treated as SIS_IDs.

---

## 9. Workflow Test Harness

### 9a. Open Test Harness

**Steps:**

1. Click the **JQ Lab** tab.
2. Click the **Test Harness** sub-tab at the top.

**Expected outcome:** The Test Harness panel loads with a workflow dropdown, input JSON textarea, task mocks textarea, and a presets list.

### 9b. Load a preset

**Steps:**

1. In the Presets section, click **Apply** next to "Person created in Colleague".

**Expected outcome:** The Workflow dropdown selects `student_enrollment`, the Workflow Input textarea fills with the person payload, and the Task Mocks textarea fills with the mock output definitions.

### 9c. Load task reference names

**Steps:**

1. Select `student_enrollment` from the Workflow dropdown.
2. Click **Load Task Refs**.

**Expected outcome:** A Task Reference Names card appears listing all task reference names in the workflow (e.g., `ethos_get_person_ref`, `enroll_ref`). Each has an **Add Mock** button.

### 9d. Add a task mock

**Steps:**

1. Click **Add Mock** next to a task reference name.

**Expected outcome:** The Task Mocks textarea gains an entry for that task reference with an empty `outputData` object. You can now fill in the desired output.

### 9e. Run a test

**Steps:**

1. With a workflow and mocks configured, click **Run Test**.

**Expected outcome:** The Test Result card appears showing the workflow execution status (COMPLETED or FAILED), a table of tasks with their statuses and durations, and the workflow output. A "simulated" badge confirms this ran in mock mode.

### 9f. Verify Ethos 404 preset causes failure

**Steps:**

1. Apply the **Ethos 404 error** preset.
2. Click **Run Test**.

**Expected outcome:** The Test Result shows status `FAILED`. The task table shows the `ethos_get_person_ref` task as FAILED with HTTP_404 in its output.

### 9g. Save a custom preset

**Steps:**

1. Configure a custom workflow input and task mocks.
2. Click **Save as Preset**.
3. Enter a name when prompted.

**Expected outcome:** The preset appears in the Presets list for future use.

---

## 10. Performance Digest

### 10a. Load digest

**Steps:**

1. Click the **Digest** tab.

**Expected outcome:** The page auto-loads the daily digest. The Workflow Performance table shows a row for each workflow with total executions, failures, failure percentage, average duration, and a trend arrow.

### 10b. Read recommendations

**Steps:**

1. The Recommendations section at the top of the Digest tab is visible.

**Expected outcome:** If any workflows have failure rates above 5%, they appear with orange (warning) or red (error) severity badges. Worker health issues and performance regressions also appear here. If everything is healthy, a green "No issues found" message is shown.

### 10c. Check trend arrows

**Expected outcome:**
- `↑` (up arrow) in red means the workflow is slower than its 7-day average.
- `↓` (down arrow) in green means it is faster.
- `→` (right arrow) in gray means performance is stable.
- `new` means there is no historical data to compare against.

### 10d. Check regressions

**Expected outcome:** If any workflow is more than 50% slower than its 7-day average, it appears in a red Regressions section at the bottom of the page with the current and historical average durations.

### 10e. Check workflow history via API

**Steps:**

1. Run:
   ```
   curl.exe -s http://localhost:5000/api/v1/digest/workflow/student_enrollment/history
   ```

**Expected outcome:** A JSON object with `name` and a `history` array of up to 7 entries, each with `date`, `total`, `failed`, and `avg_ms`.

### 10f. Refresh digest

**Steps:**

1. Click the **Refresh** button in the Digest tab.

**Expected outcome:** The digest regenerates and the "Generated:" timestamp updates to the current time.

---

## 11. Mock/Live Signal & Production-Safety Warnings

These checks verify the app correctly signals whether it is on fixture data or a real Conductor, and that destructive surfaces are guarded in live mode. See `warning.md` for the full list of caustic operations.

### 11a. Mock-mode signals

**Goal:** Confirm the app advertises mock mode when `CONDUCTOR_URL` is unset.

**Steps:**

1. Ensure `CONDUCTOR_URL` is empty/unset in `.env`, then start the app.
2. Open `http://localhost:5000` and look at the navigation bar.
3. Run `curl.exe -s -i http://localhost:5000/api/v1/health` and read the response headers.

**Expected outcome:**

- An amber **MOCK** chip is visible in the navbar; no green LIVE chip.
- No live-environment banner appears across the top of the page.
- The response includes the header `X-Mock-Mode: true`.

### 11b. Live-mode signals

**Goal:** Confirm the app advertises live mode when `CONDUCTOR_URL` is set.

**Steps:**

1. Set `CONDUCTOR_URL` to a real Conductor URL in `.env` and restart the app.
2. Open `http://localhost:5000` and look at the navigation bar and top of page.
3. Run `curl.exe -s -i http://localhost:5000/api/v1/health` and read the response headers.

**Expected outcome:**

- A green **LIVE** chip is visible in the navbar; no amber MOCK chip.
- An amber **LIVE environment** banner appears across the top of the page.
- The response does **not** include an `X-Mock-Mode` header.

### 11c. Per-section live warnings

**Goal:** Confirm destructive tabs show inline warnings in live mode.

**Steps:**

1. With the app in live mode (11b), open the Settings, Reconciler, and Migrations tabs, plus the JQ Lab → Test Harness sub-tab, in turn.

**Expected outcome:** each of the four surfaces shows an inline **⚠ LIVE** warning callout describing the production impact. In mock mode (11a) none of these callouts appear.

### 11d. Destructive-action confirmation

**Goal:** Confirm destructive buttons require confirmation in live mode.

**Steps:**

1. With the app in live mode, go to Settings and click **Delete** on a secret — then cancel the dialog.
2. Go to Migrations, open a batch, and click **Retry Failures** — then cancel the dialog.
3. Go to Reconciler, select a failure group, and click **Bulk Retry Selected** — then cancel the dialog.

**Expected outcome:** each click raises a confirmation dialog that names the action and its production impact. Cancelling the dialog performs no action. (In mock mode the same buttons show only a short confirmation.)
