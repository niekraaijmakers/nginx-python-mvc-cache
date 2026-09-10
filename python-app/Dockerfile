FROM python:3.12-slim
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY run.py ./
EXPOSE 3000
# --timeout-keep-alive default fine; workers=2 for a bit of concurrency
CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "3000", "--workers", "2"]
