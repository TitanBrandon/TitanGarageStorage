FROM node:24-bookworm-slim AS frontend
WORKDIR /app

COPY package.json package-lock.json ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    npm ci --no-audit --no-fund
COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY backend/requirements-hosted.txt ./backend/requirements-hosted.txt
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    python -m pip install --no-cache-dir -r backend/requirements-hosted.txt
COPY backend ./backend
COPY --from=frontend /app/dist ./dist
RUN chmod -R a=rX /app

USER 10001:10001
EXPOSE 10000
CMD ["python", "-m", "backend.hosted"]
