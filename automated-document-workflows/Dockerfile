FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /app

# Install system dependencies for document processing
RUN apt-get update && apt-get install -y \
    # OCR dependencies
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-fra \
    tesseract-ocr-spa \
    tesseract-ocr-deu \
    # PDF processing
    poppler-utils \
    ghostscript \
    qpdf \
    # WeasyPrint dependencies
    wkhtmltopdf \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    # Image processing
    libmagickwand-dev \
    imagemagick \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    # System utilities
    curl \
    wget \
    unzip \
    git \
    # Build dependencies
    gcc \
    g++ \
    make \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Configure ImageMagick security policy for PDF processing
RUN sed -i 's/^.*policy domain="coder".*pattern="PDF".*$/  <policy domain="coder" rights="read|write" pattern="PDF" \/>/' /etc/ImageMagick-6/policy.xml

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/temp /app/outputs /app/data /app/quarantine /app/logs

# Set permissions
RUN chmod +x /app/scripts/*.sh 2>/dev/null || true

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["python", "-m", "app.main"]