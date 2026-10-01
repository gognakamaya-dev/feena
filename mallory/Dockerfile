FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[mcp]' && python -m playwright install --with-deps chromium \
    && useradd --create-home mallory && mkdir /data && chown mallory:mallory /data
USER mallory
EXPOSE 3000
ENTRYPOINT ["mallory-mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "3000", "--out", "/data/runs"]
