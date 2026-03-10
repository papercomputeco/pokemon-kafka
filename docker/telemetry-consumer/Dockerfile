FROM python:3.12-slim
RUN pip install --no-cache-dir confluent-kafka
COPY consumer.py /app/consumer.py
WORKDIR /app
CMD ["python", "consumer.py"]
