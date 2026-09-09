FROM python:3.12-slim
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY run.py ./
EXPOSE 3000
# --timeout 5: don't let a hung worker (e.g. blocked on Redis) sit forever
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:3000", "--timeout", "5", "run:app"]
