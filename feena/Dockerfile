FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[mcp]' && python -m playwright install --with-deps chromium \
    && useradd --create-home feena && mkdir /data && chown feena:feena /data
USER feena
EXPOSE 3000
ENTRYPOINT ["feena-mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "3000", "--out", "/data/runs"]
