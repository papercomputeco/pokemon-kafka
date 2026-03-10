-- Source table: reads raw telemetry from Kafka
CREATE TABLE agent_telemetry_raw (
    `hash` STRING,
    `parent` STRING,
    `role` STRING,
    `content` STRING,
    `model` STRING,
    `timestamp` STRING,
    `tokens_in` INT,
    `tokens_out` INT,
    `latency_ms` INT,
    `session_id` STRING,
    `turn` INT,
    `event_time` AS TO_TIMESTAMP(`timestamp`),
    WATERMARK FOR `event_time` AS `event_time` - INTERVAL '5' SECONDS
) WITH (
    'connector' = 'kafka',
    'topic' = 'agent.telemetry.raw',
    'properties.bootstrap.servers' = 'kafka:29092',
    'properties.group.id' = 'flink-telemetry',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json'
);

-- Sink table: writes alerts to Kafka
CREATE TABLE agent_telemetry_alerts (
    `alert_type` STRING,
    `session_id` STRING,
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

-- Stuck loop detection: same tool_call content 3+ times in 30s window
INSERT INTO agent_telemetry_alerts
SELECT
    'STUCK_LOOP' AS alert_type,
    session_id,
    content AS detail,
    window_start,
    window_end,
    COUNT(*) AS event_count
FROM TABLE(
    TUMBLE(
        TABLE agent_telemetry_raw,
        DESCRIPTOR(event_time),
        INTERVAL '30' SECONDS
    )
)
WHERE role = 'tool_call'
GROUP BY session_id, content, window_start, window_end
HAVING COUNT(*) >= 3;

-- Token spike detection: tokens_in > 2x the average over a 2-minute tumbling window
INSERT INTO agent_telemetry_alerts
SELECT
    'TOKEN_SPIKE' AS alert_type,
    session_id,
    CONCAT('avg_tokens=', CAST(CAST(avg_tokens AS INT) AS STRING),
           ' max_tokens=', CAST(max_tokens AS STRING)) AS detail,
    window_start,
    window_end,
    cnt AS event_count
FROM (
    SELECT
        session_id,
        window_start,
        window_end,
        AVG(tokens_in) AS avg_tokens,
        MAX(tokens_in) AS max_tokens,
        COUNT(*) AS cnt
    FROM TABLE(
        TUMBLE(
            TABLE agent_telemetry_raw,
            DESCRIPTOR(event_time),
            INTERVAL '2' MINUTES
        )
    )
    WHERE role = 'assistant' AND tokens_in > 0
    GROUP BY session_id, window_start, window_end
)
WHERE max_tokens > avg_tokens * 2.0;
