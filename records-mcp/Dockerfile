# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATIENT_DATA_DIR=/data/patients \
    MCP_VERIFICATION_KEY=/run/secrets/mcp-verification-key.pem \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8001 \
    APP_ENV=local \
    OTEL_SERVICE_NAME=clinician-records-mcp

WORKDIR /app

RUN addgroup --system records && adduser --system --ingroup records records

COPY pyproject.toml README.md ./
COPY src ./src
COPY schemas ./schemas

RUN pip install --upgrade pip && pip install .

USER records

EXPOSE 8001

CMD ["python", "-m", "clinician_records", "--host", "0.0.0.0", "--port", "8001"]
