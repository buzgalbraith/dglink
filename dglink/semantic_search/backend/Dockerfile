FROM python:3.10-slim

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/main.py .

RUN mkdir /app/resources
COPY neo4j/*.tsv /app/resources

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]