FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt



COPY app.py .
COPY templates/ templates/  
COPY static/ static/  
ARG PORTAL_NAME
RUN apt-get update && apt-get install -y --no-install-recommends gettext-base && rm -rf /var/lib/apt/lists/*
RUN envsubst '${PORTAL_NAME}' < /app/templates/index_template.html > /app/templates/index.html

CMD ["python", "app.py"]

