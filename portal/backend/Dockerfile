FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    && pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

COPY . .

EXPOSE 8000

# 生产模式: gunicorn + uvicorn workers,多进程,无热重载
# WORKERS / TIMEOUT 可通过环境变量在 docker-compose 中覆盖
ENV GUNICORN_WORKERS=4 \
    GUNICORN_TIMEOUT=120

CMD ["sh", "-c", "gunicorn main:app -k uvicorn.workers.UvicornWorker -w ${GUNICORN_WORKERS} -b 0.0.0.0:8000 --timeout ${GUNICORN_TIMEOUT} --access-logfile - --error-logfile -"]
