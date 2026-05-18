-- Conductor Companion — PostgreSQL schema initialization
-- Run this against the conductor_companion database before first use.

-- ------------------------------------------------------------
-- Create tables
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS saved_searches (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL UNIQUE,
    description TEXT         NOT NULL DEFAULT '',
    search_config JSONB      NOT NULL DEFAULT '{}',
    created_by  VARCHAR(100) NOT NULL DEFAULT 'user',
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    use_count   INTEGER      NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS migration_batches (
    id                    SERIAL PRIMARY KEY,
    name                  VARCHAR(200) NOT NULL,
    workflow_name         VARCHAR(200) NOT NULL,
    started_at            TIMESTAMP    NOT NULL DEFAULT NOW(),
    correlation_id_prefix VARCHAR(200) NOT NULL DEFAULT '',
    total_expected        INTEGER      NOT NULL DEFAULT 0,
    created_by            VARCHAR(100) NOT NULL DEFAULT 'user',
    notes                 TEXT         NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS jq_expressions (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(200) NOT NULL UNIQUE,
    description   TEXT         NOT NULL DEFAULT '',
    expression    TEXT         NOT NULL,
    resource_name VARCHAR(200) NOT NULL DEFAULT '',
    use_case      VARCHAR(200) NOT NULL DEFAULT '',
    created_by    VARCHAR(100) NOT NULL DEFAULT 'user',
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    use_count     INTEGER      NOT NULL DEFAULT 0,
    tags          VARCHAR(500) NOT NULL DEFAULT ''
);

-- ------------------------------------------------------------
-- Pre-seeded saved searches
-- ------------------------------------------------------------

INSERT INTO saved_searches (name, description, search_config, created_by) VALUES
(
    'All Failed Today',
    'Show all FAILED workflows started in the last 24 hours',
    '{"status": "FAILED", "query": "startTime > NOW()-1d"}',
    'system'
),
(
    'Running Order Fulfillment',
    'Active order_fulfillment workflow executions',
    '{"workflowType": "order_fulfillment", "status": "RUNNING"}',
    'system'
),
(
    'Failed Financial Aid',
    'Failed financial_aid_processing workflows for review',
    '{"workflowType": "financial_aid_processing", "status": "FAILED"}',
    'system'
),
(
    'Recent Student Enrollments',
    'All student_enrollment workflows regardless of status',
    '{"workflowType": "student_enrollment", "size": 50}',
    'system'
),
(
    'Payroll Errors This Month',
    'Failed payroll_processing workflows from the current month',
    '{"workflowType": "payroll_processing", "status": "FAILED", "query": "startTime > NOW()-30d"}',
    'system'
)
ON CONFLICT (name) DO NOTHING;

-- ------------------------------------------------------------
-- Pre-loaded JQ expressions
-- ------------------------------------------------------------

INSERT INTO jq_expressions (name, description, expression, resource_name, use_case, created_by, tags) VALUES
(
    'Extract Output Keys',
    'List all top-level keys in a task output',
    'keys',
    'any',
    'Exploration',
    'system',
    'utility,keys'
),
(
    'Filter Completed Tasks',
    'Return only tasks with COMPLETED status',
    '.tasks[] | select(.status == "COMPLETED")',
    'workflow',
    'Task filtering',
    'system',
    'tasks,filter'
),
(
    'Get First Failed Task',
    'Find the first task that failed in an execution',
    'first(.tasks[] | select(.status == "FAILED"))',
    'workflow',
    'Debugging',
    'system',
    'tasks,debug,failed'
),
(
    'Pluck Order IDs',
    'Extract orderId from workflow input across a results array',
    '[.results[].input.orderId]',
    'search_results',
    'Batch extraction',
    'system',
    'input,extract,batch'
),
(
    'Workflow Status Summary',
    'Count executions by status from a search result set',
    '.results | group_by(.status) | map({status: .[0].status, count: length}) | sort_by(.count) | reverse',
    'search_results',
    'Reporting',
    'system',
    'summary,reporting,status'
),
(
    'Deep Nested Value',
    'Safely navigate a deeply nested path, returning null if missing',
    '.tasks[]?.outputData?.result?.value // null',
    'task_output',
    'Safe field access',
    'system',
    'nested,safe,outputData'
),
(
    'Correlation IDs List',
    'Collect all correlationId values from a search result',
    '[.results[].correlationId] | unique | sort',
    'search_results',
    'Batch operations',
    'system',
    'correlationId,list,batch'
)
ON CONFLICT (name) DO NOTHING;
