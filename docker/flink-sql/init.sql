-- Source table: reads tapes.node.v1 events from Kafka
-- The content array field is omitted (complex nested structure
-- not needed for anomaly detection).
CREATE TABLE tapes_events (
    `schema` STRING,
    `root_hash` STRING,
    `occurred_at` TIMESTAMP(3),
    `node` ROW<
        `hash` STRING,
        `parent_hash` STRING,
        `bucket` ROW<
            `type` STRING,
            `role` STRING,
            `model` STRING,
            `provider` STRING,
            `agent_name` STRING
        >,
        `stop_reason` STRING,
        `usage` ROW<
            `input_tokens` INT,
            `output_tokens` INT
        >,
        `project` STRING
    >,
    WATERMARK FOR `occurred_at` AS `occurred_at` - INTERVAL '5' SECONDS
) WITH (
    'connector' = 'kafka',
    'topic' = 'agent.telemetry.raw',
    'properties.bootstrap.servers' = 'kafka:29092',
    'properties.group.id' = 'flink-telemetry',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json',
    'json.timestamp-format.standard' = 'ISO-8601',
    'json.ignore-parse-errors' = 'true'
);

-- Sink table: writes alerts to Kafka
CREATE TABLE tapes_alerts (
    `alert_type` STRING,
    `root_hash` STRING,
    `detail` STRING,
    `window_start` TIMESTAMP(3),
    `window_end` TIMESTAMP(3),
    `event_count` BIGINT
) WITH (
    'connector' = 'kafka',
    'topic' = 'agent.telemetry.alerts',
    'properties.bootstrap.servers' = 'kafka:29092',
    'format' = 'json'
);

-- Stuck loop detection: 10+ assistant turns in a 30s window per conversation
INSERT INTO tapes_alerts
SELECT
    'STUCK_LOOP' AS alert_type,
    root_hash,
    node.bucket.role AS detail,
    window_start,
    window_end,
    COUNT(*) AS event_count
FROM TABLE(
    TUMBLE(
        TABLE tapes_events,
        DESCRIPTOR(occurred_at),
        INTERVAL '30' SECONDS
    )
)
WHERE node.bucket.role = 'assistant'
GROUP BY root_hash, node.bucket.role, window_start, window_end
HAVING COUNT(*) >= 10;

-- Token spike detection: max input_tokens > 2x average over 2-minute window
INSERT INTO tapes_alerts
SELECT
    'TOKEN_SPIKE' AS alert_type,
    root_hash,
    CONCAT('avg_tokens=', CAST(CAST(avg_tokens AS INT) AS STRING),
           ' max_tokens=', CAST(max_tokens AS STRING)) AS detail,
    window_start,
    window_end,
    cnt AS event_count
FROM (
    SELECT
        root_hash,
        window_start,
        window_end,
        AVG(node.usage.input_tokens) AS avg_tokens,
        MAX(node.usage.input_tokens) AS max_tokens,
        COUNT(*) AS cnt
    FROM TABLE(
        TUMBLE(
            TABLE tapes_events,
            DESCRIPTOR(occurred_at),
            INTERVAL '2' MINUTES
        )
    )
    WHERE node.bucket.role = 'assistant' AND node.usage.input_tokens > 0
    GROUP BY root_hash, window_start, window_end
)
WHERE max_tokens > avg_tokens * 2.0;
