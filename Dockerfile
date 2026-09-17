FROM python:3.11-slim

WORKDIR /app

# 系统依赖：matplotlib 中文字体
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

WORKDIR /app/backend
CMD ["sh", "-c", "python -m scripts.seed_demo && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
