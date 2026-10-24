# App image. Dependencies live in dialtwin-base (see Dockerfile.base).
FROM dialtwin-base
WORKDIR /app
COPY engine /app/engine
COPY studio /app/studio
ENV PYTHONUNBUFFERED=1
# HOST defaults to localhost: the UI has no login. Set HOST=0.0.0.0 in .env to reach it from your LAN.
CMD ["sh", "-c", "exec python3 -m uvicorn studio.app:app --host \"${HOST:-127.0.0.1}\" --port \"${PORT:-8097}\""]
