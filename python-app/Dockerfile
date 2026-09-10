FROM python:3.12-slim
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY run.py ./
EXPOSE 3000
# --reload watches ./app for changes (bind-mounted over this directory in
# docker-compose.yml, so edits on the host take effect without a rebuild).
# Note: --reload only works with a single worker, so --workers is dropped
# here - fine for a teaching demo, not meant for production concurrency.
CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "3000", "--reload", "--reload-dir", "app"]
