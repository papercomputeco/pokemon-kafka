FROM python:3.12-slim
RUN pip install --no-cache-dir confluent-kafka
COPY consumer.py /app/consumer.py
WORKDIR /app
# python:slim ships no pgrep, so the old `pgrep -f` check failed on every start and
# reported a working container as unhealthy forever. The script runs as PID 1 (exec-form
# CMD), so its liveness is readable straight from /proc — no extra package needed.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD grep -q consumer.py /proc/1/cmdline || exit 1
CMD ["python", "consumer.py"]
