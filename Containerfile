FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files from build context to /app
COPY . .

RUN chmod +x ./src/main.sh

EXPOSE 8000

ENTRYPOINT ["./src/main.sh"]
CMD ["--dev"]

# podman compose up --build
# podman compose down
# podman system prune
