FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    DATABASE_URL=sqlite:////data/database.db \
    LOG_DIR=/data/logs

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Непривилегированный пользователь; /data — каталог для БД и логов (монтируется как volume)
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data \
    && chown -R app:app /data /app
USER app

VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','8000'), timeout=4)"

# Один воркер обязателен: иначе планировщик запустится в каждом воркере (как в Procfile)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
