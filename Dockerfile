# Sử dụng Python image có sẵn các dependency cho Playwright
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Đặt thư mục làm việc
WORKDIR /app

# Copy file requirements và cài đặt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cài đặt trình duyệt Playwright (chỉ chromium)
RUN playwright install chromium

# Copy toàn bộ code vào container
COPY . .

# Mở cổng 5000 cho Flask
EXPOSE 5000

# Biến môi trường để chạy headless
ENV HEADLESS=true
ENV PORT=5000

# Lệnh khởi chạy
CMD ["python", "main.py"]
