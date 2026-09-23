FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY server/ ./server/
COPY examples/ ./examples/
COPY --from=web /web/dist ./web/dist
RUN useradd --create-home quest && mkdir -p /data && chown quest:quest /data
USER quest
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "server", "--host", "0.0.0.0", "--port", "8000"]
