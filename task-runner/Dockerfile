FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/install -r requirements.txt

FROM gcr.io/distroless/python3-debian12:nonroot
COPY --from=builder /install /usr/local/lib/python3.11/site-packages
COPY main.py /app/main.py
ENV PYTHONPATH=/usr/local/lib/python3.11/site-packages
WORKDIR /workspace
ENTRYPOINT ["python3", "/app/main.py"]
