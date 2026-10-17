FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

ENV PYTHONUNBUFFERED=1
ENV DATA_FILEPATH=/app/data/data.txt

CMD ["python", "main.py"]
