FROM python:3.11-slim
WORKDIR /app
COPY ./requirements.txt .
RUN pip install -r requirements.txt
COPY app.py .
COPY templates/ ./templates/
COPY static/ ./static/
RUN apt-get update && apt-get install -y --no-install-recommends gettext-base && rm -rf /var/lib/apt/lists/*
CMD ["python", "app.py"]
