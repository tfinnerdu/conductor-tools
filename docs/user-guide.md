# Conductor Companion — User Guide

Welcome to Conductor Companion, a web tool that extends Orkes Conductor's built-in UI with features designed for the Doane platform team. This guide walks you through each feature as if you have just opened the app for the first time.

---

## Getting Started

Open your browser and go to `http://localhost:5000` (or the URL your team uses for the deployed version on `du-int.doane.edu`).

You will see the orange Doane top bar and a row of tabs across the navy navigation bar. Each tab is one feature area. Click a tab to switch to it.

If Conductor is not running or unreachable, the app automatically returns realistic demo data so you can explore without a live connection.

---

## Search Tab

The Search tab lets you find workflow executions using a combination of filters, then export the results to a spreadsheet.

**Finding workflows by type and status**

Use the Workflow Type dropdown to pick a specific workflow (for example, `order_fulfillment`). Use the Status radio buttons to narrow down to Completed, Failed, Running, or Paused executions. Click **Search** and the results appear in the table below with a status count summary at the top.

**Using the free text box**

If you know part of a correlation ID, workflow ID, or other value, type it in the Free Text box. Conductor's full-text index will match it against your executions.

**Adding input field filters**

Sometimes you want to narrow results based on a field inside the workflow's input payload — for example, only executions where `input.customerId` equals a specific value. Click **+ Add Filter**, enter the JSON path (dot notation like `input.customerId`), pick an operator (equals, contains, exists, etc.), and type the expected value. You can add as many filter rows as you need.

**Exporting to CSV**

Once you have the results you want, click **Export CSV**. A file called `workflow_search_results.csv` will download. Each row contains the workflow ID, type, status, correlation ID, start time, end time, and version.

**Saving and reusing searches**

If you run the same search regularly, click **Save Search** and give it a name. The saved search appears in the panel on the right side. Next time you need it, click the saved search and it runs immediately. Use the X button to remove a saved search you no longer need.

---

## JQ Lab Tab

The JQ Lab is a playground for writing and testing jq expressions against real Conductor task output. It is useful when you need to figure out the right expression for a `JSON_JQ_TRANSFORM` task in a workflow.

**Evaluating an expression**

Paste your JSON data into the **Input JSON** textarea on the left. Type your jq expression in the **JQ Expression** textarea on the right. Click **Evaluate**. The result appears below the buttons. If the expression has a syntax error, an error message appears in the red box instead.

**Loading real output from Conductor**

Instead of pasting JSON manually, you can pull the output of a specific task directly from a live Conductor execution. Enter the workflow execution ID in the Load from Execution section. You can also specify a task reference name if you want a particular task's output. Click **Load Output** and the task's outputData is placed into the Input JSON textarea automatically.

**Saving to the library**

Once you have an expression that works, click **Save to Library**. Give it a name and a description. It will appear in the Expression Library panel at the bottom of the page. Anyone on the team can open it in the lab with one click.

**Generating a Conductor task definition**

When you have an expression ready to use in production, click **Copy as Conductor Task**. This wraps your expression in the correct `JSON_JQ_TRANSFORM` task JSON and copies it to your clipboard. Paste it into your workflow definition.

---

## Workers Tab

The Workers tab shows you the health of all Conductor workers in real time. It refreshes automatically every 5 seconds.

**Reading the table**

Each row represents one task type. The columns are:

- **Task Type** — the name of the task workers are polling for.
- **Workers** — how many distinct worker IDs have polled recently.
- **Last Poll** — how long ago the most recent poll happened (e.g., "2s", "45s").
- **Queue Depth** — how many tasks are waiting in the queue right now.
- **Status** — a color-coded health classification:
  - Green **healthy** — polled within the last 5 seconds.
  - Yellow **slow_poll** — last poll was 5–30 seconds ago. Workers may be busy or slow.
  - Red **down** — no poll in 30+ seconds. This worker is likely down.
  - Red **no_workers** — no worker IDs have registered for this task type at all.

**Viewing performance stats**

Click any row and a performance panel slides open below the table. It shows total executions, success rate, failure count, and duration percentiles (p50, p95, p99) for that task type.

**The refresh counter**

The "Last refreshed: Xs ago" label in the top right of the card counts up from zero and resets each time the table refreshes. If it climbs above 10 seconds, something may be wrong with the refresh cycle.

---

## Migrations Tab

The Migrations tab helps you track and manage large batch operations where many workflow executions are kicked off together under a common correlation ID prefix.

**Creating a batch**

Fill in the **New Batch** form on the right side:

- **Batch Name** — a human-readable label for this migration run.
- **Workflow Name** — the workflow type all executions in this batch use.
- **Correlation ID Prefix** — the prefix shared by all correlation IDs in this batch (for example, `migration-q1-2024-`). Leave blank if you are not using a prefix filter.
- **Expected Count** — how many total executions you expect. Used to calculate the progress percentage.

Click **Create Batch**. The batch appears on the left side.

**Checking status**

Click **Refresh** on a batch card. The tool pages through all Conductor search results for that workflow type and correlation prefix, tallies the statuses, and shows a progress bar and status counts.

**Retrying failed executions**

Click **Retry Failures** on a batch card. After you confirm, the tool finds every FAILED execution in the batch and calls Conductor's retry endpoint for each one. A toast message tells you how many were retried.

**Exporting failures to CSV**

Click **Export CSV** to download a spreadsheet of every FAILED execution in the batch. This is useful for handing off to an operations team or for auditing.

---

## Diff Tab

The Diff tab lets you compare two versions of a workflow definition and understand what changed between them.

**Comparing versions**

Select a workflow from the dropdown. Version A and Version B dropdowns populate automatically. Choose the two versions you want to compare. Select a diff mode:

- **Full JSON** — compares the entire workflow definition.
- **Tasks Only** — compares just the tasks array, which is usually the most relevant part.
- **Significant Changes** — shows only lines that changed a task name, type, reference name, or input parameters.

Click **Compare**. Green lines are additions, red lines are removals, and blue lines are section headers from the diff.

**Dependency map**

Click **Load Dependency Map** to see a table of every workflow version and the task types it uses. This helps you understand which workflows depend on which tasks.

**Impact analysis**

If you are planning to change a task type (rename it, update its inputs, etc.), use the Impact Analysis panel to find out which workflow versions will be affected. Enter the task type name and click **Analyze Impact**. The result shows each workflow version that references that task type, along with the task reference names used.

---

## Reconciler Tab

The Reconciler tab groups failed workflow executions by the task type that caused the failure. This makes it easy to spot patterns (for example, "12 failures all caused by `ethos_get_person` returning HTTP 404") and retry them in bulk.

**Reading the failure summary**

When you open the tab, the app loads a summary of all failures in the last 24 hours. The top section shows total failures across all workflows. Below that, each workflow is broken down by task type with error code counts (e.g., `HTTP_404 x7`, `TIMEOUT x2`).

**Changing the time window**

Use the **Hours back** dropdown to change the look-back window from 6 to 72 hours. The summary refreshes automatically.

**Retrying a failure group**

In the Failures by Task Type table, click **Retry All** next to any task type to retry all executions in that group at once.

**Bulk retry with checkboxes**

Check one or more task type rows using the checkboxes on the left. A **Bulk Retry Selected** button appears at the bottom of the page. Click it to retry all selected executions in a single API call. The result shows how many were successfully retried and how many errored.

**Drilling into a single execution**

Use the API directly to inspect one execution in detail:
```
GET /api/v1/reconciler/failures/<workflow_id>
```
The response includes the failed task type, the exact error message, a short extracted error code (like `HTTP_404` or `DUPLICATE_VALUE`), the retry count, and the workflow input (including `sisId` if present).

---

## Traces Tab

The Traces tab lets you follow a person's data through multiple systems by searching with a GUID or SIS_ID.

**Tracing by GUID or SIS_ID**

Select the search type (GUID or SIS_ID) using the radio buttons. Type the identifier in the text box and click **Trace**. The app searches Conductor for any workflow execution that mentions the identifier, and also does a mock Salesforce lookup.

**Reading the timeline**

The Event Timeline shows events sorted by time (oldest first). Each event has:

- A system badge (CONDUCTOR in navy, SALESFORCE in blue)
- A status icon: green checkmark for OK, red X for error, yellow warning for issues
- The event name and a short detail string
- For Salesforce events: the records found (with ID, name, and SIS_ID__c if present)

**Diagnosis message**

Below the search form, a colored diagnosis message summarizes what was found:
- Green: everything looks healthy
- Yellow: a warning, such as a record missing its SIS_ID__c
- Red: an error, such as no record found or a duplicate

**Recent traces**

The Recent Traces section at the bottom shows the last 20 trace searches with timestamps, the identifier used, event counts, and whether any errors were found. Click **Retrace** to re-run any previous search.

---

## JQ Lab — Test Harness Sub-Tab

Inside the JQ Lab tab there is now a **Test Harness** sub-tab alongside Sandbox and Library.

**Running a test**

Select a workflow from the dropdown, optionally set a version number, fill in the Workflow Input JSON, and add Task Mocks for any tasks you want to override. Click **Run Test**. In mock mode (no live Conductor), the execution is simulated in-process using the workflow definition. The Test Result card shows the execution status, a task-by-task breakdown, and the workflow output.

**Using built-in presets**

Four presets are pre-loaded to represent common Doane scenarios:

- **Person created in Colleague** — a new person flowing through `student_enrollment` with a full Ethos person payload.
- **Person address updated** — an address-change event with the updated address in the mock output.
- **Application submitted** — an admissions application with payment charged.
- **Ethos 404 error** — demonstrates what happens when `ethos_get_person` cannot find the record. The test run will show a FAILED status.

Click **Apply** next to any preset to load it into the form. Then click **Run Test**.

**Loading task reference names**

After selecting a workflow, click **Load Task Refs** to see a list of all task reference names in the workflow definition. Each has an **Add Mock** button that inserts an empty mock entry into the Task Mocks textarea so you can fill in the desired output.

**Saving a custom preset**

After configuring a test you want to reuse, click **Save as Preset** and give it a name. It will appear in the Presets list for all future sessions.

---

## Digest Tab

The Digest tab shows a daily performance summary across all watched workflows, with recommendations for issues that need attention.

**Recommendations**

The top section shows actionable recommendations color-coded by severity:
- Red (error): workflows with failure rates above 20%, workers that are down, or workers with no registered pollers.
- Orange (warning): workflows with failure rates above 5%, workers that are slow to poll, or performance regressions.

If everything is healthy, a green "No issues found" message is shown.

**Workflow Performance table**

Each workflow has a row showing:
- **Total** — executions in the period
- **Failed** — how many failed
- **Failure %** — failure rate (red if above 20%, orange if above 5%)
- **Avg ms** — average execution duration
- **Trend** — direction compared to the 7-day average: up arrow means slower, down arrow means faster, right arrow means stable, "new" means no history

**Regressions**

If any workflow is more than 50% slower than its 7-day average, it appears in a red Regressions section at the bottom of the page.

**Refreshing**

Click the **Refresh** button to regenerate the digest on demand. The "Generated:" timestamp updates. The digest is also regenerated automatically at 06:00 UTC daily.
