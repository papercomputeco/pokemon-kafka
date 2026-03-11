FROM python:3.12-slim
RUN pip install --no-cache-dir confluent-kafka
COPY consumer.py /app/consumer.py
COPY tape_writer.py /app/tape_writer.py
WORKDIR /app
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD pgrep -f consumer.py || exit 1
CMD ["python", "consumer.py"]
