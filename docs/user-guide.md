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

## Traces Tab (Coming Soon)

The Traces tab will provide distributed trace visualization for Conductor executions. This is planned for Phase 2.

---

## Digest Tab (Coming Soon)

The Digest tab will provide a configurable daily summary of workflow activity, failure trends, and worker health metrics. Delivery via email or Slack is planned for Phase 2.
