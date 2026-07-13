FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_PATH=/app/output/solar.json

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .


FROM base AS test

COPY tests ./tests
RUN pip install --no-cache-dir 'pytest>=8,<9' && pytest


FROM base AS runtime

RUN addgroup --system publisher && adduser --system --ingroup publisher publisher
RUN mkdir -p /app/output && chown publisher:publisher /app/output
USER publisher

VOLUME ["/app/output"]
CMD ["victron-gx-publisher"]
