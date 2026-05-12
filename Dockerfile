FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Environment settings for faster logging
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

EXPOSE 10000

CMD ["python", "main.py"]
