FROM python:3.11-slim

WORKDIR /app

COPY ./requirements.txt .
COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /bin/
RUN uv venv && uv pip install -r requirements.txt

# Copy application files
COPY app.py .
COPY templates/ ./templates/

# Expose port
EXPOSE 5000

# Run the application
CMD ["uv", "run", "python", "app.py"]