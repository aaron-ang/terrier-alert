FROM python:3.11-slim

EXPOSE 8000

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy all files from build context to /app
COPY . .

CMD ["python3", "test/bot.py"]

# docker compose build
# docker compose up
# docker system prune
