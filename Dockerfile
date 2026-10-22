FROM node:24-slim AS dashboard
WORKDIR /dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

FROM python:3.14-slim AS docs
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN git clone --depth 1 --branch 0.150.0 --filter=blob:none --sparse https://github.com/fastapi/fastapi data/fastapi-0.150.0 \
    && git -C data/fastapi-0.150.0 sparse-checkout set docs/en/docs docs_src
COPY pinpoint_docs/ pinpoint_docs/
COPY evals/questions.json evals/
RUN python -m pinpoint_docs.chunk

FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pinpoint_docs/ pinpoint_docs/
COPY evals/ evals/
COPY --from=docs /app/data/chunks.jsonl data/chunks.jsonl
COPY --from=dashboard /dashboard/dist dashboard/dist
EXPOSE 8000
CMD ["sh", "-c", "[ -f data/chroma/chroma.sqlite3 ] || python -m pinpoint_docs.index; exec fastapi run pinpoint_docs/api.py --host 0.0.0.0 --port 8000"]
