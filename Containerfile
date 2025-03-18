FROM python:3.11-slim

EXPOSE 8000

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy all files from build context to /app
COPY . .

RUN ["chmod", "+x", "./src/main.sh"]

CMD ["./src/main.sh", "--dev"]

# podman compose up --build
# podman compose down
# podman system prune
