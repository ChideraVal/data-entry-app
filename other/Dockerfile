# ---------- Base Image ----------
FROM python:3.13-slim

# Prevent Python from buffering stdout
ENV PYTHONUNBUFFERED=1

# ---------- System Dependencies ----------
# Install poppler (for pdf2image)
# Install tesseract OCR (for pytesseract)
# Install additional utilities for PDFs/images
RUN apt-get update && \
    apt-get install -y \
        poppler-utils \
        tesseract-ocr \
        libtesseract-dev \
        ghostscript \
        libjpeg62-turbo-dev \
        zlib1g-dev \
        libpng-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ---------- Create App Directory ----------
WORKDIR /app

# ---------- Install Python Dependencies ----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Copy All Source Code ----------
COPY . .

# ---------- Collect Static Files ----------
# If you use whitenoise or static collection, uncomment:
RUN python manage.py collectstatic --noinput

# ---------- Expose Port ----------
EXPOSE 8000

# ---------- Start Command ----------
CMD ["gunicorn", "dataproject.wsgi:application", "--bind", "0.0.0.0:8000"]
