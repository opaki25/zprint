FROM python:3.12-slim
WORKDIR /app
ENV ZPRINT_PROJECT_ROOT=/app
COPY pyproject.toml ./
COPY services ./services
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 zprint
COPY . .
RUN mkdir -p /data /agent && chown -R zprint:zprint /data /agent
USER zprint
CMD ["uvicorn", "zprint.main:app", "--host", "0.0.0.0", "--port", "8000"]
