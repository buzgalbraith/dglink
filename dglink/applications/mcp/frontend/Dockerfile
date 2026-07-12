FROM python:3.11-slim
WORKDIR /app
COPY ./requirements.txt .
COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /bin/
RUN uv venv && uv pip install -r requirements.txt
COPY app.py .
COPY templates/ ./templates/
COPY static/ ./static/
ARG FONT_SIZE
RUN apt-get update && apt-get install -y --no-install-recommends gettext-base && rm -rf /var/lib/apt/lists/*
RUN envsubst '${FONT_SIZE}' < /app/templates/index_template.html > /app/templates/index.html
EXPOSE 5000
CMD ["uv", "run", "python", "app.py"]