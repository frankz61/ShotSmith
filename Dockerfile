FROM python:3.11-slim
WORKDIR /srv
COPY . .
RUN pip install --no-cache-dir -e .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
