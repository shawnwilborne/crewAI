# Automated Document Processing Workflows

A production-ready system for end-to-end document processing, conversion, and routing with optional BaaS integration.

## 🚀 Quick Start

```bash
# Clone and setup
git clone <repository-url>
cd automated-document-workflows
cp .env.example .env

# Start with Docker
docker-compose up -d

# Or run locally
pip install -r requirements.txt
python -m app.main

# CLI Usage
python cli.py ingest data/samples/
python cli.py run JOB_ID
python cli.py route data/samples/invoice.pdf
```

## 📋 Features

- **Document Ingestion**: PDFs, images, scanned documents
- **OCR Processing**: Local OCR with Tesseract + ocrmypdf or BaaS integration
- **Format Conversion**: PDF → DOCX, images → searchable PDF
- **Template Application**: DOCX and HTML templates with Jinja2
- **Smart Routing**: YAML-based rules with regex, keywords, barcodes
- **Bates Numbering**: Sequential stamping with audit trails
- **Multi-Destination Delivery**: Local, S3, SFTP, Shopify
- **Background Processing**: Celery + Redis for scalable jobs
- **Full API**: REST endpoints for all operations
- **CLI Interface**: Command-line tools for batch operations

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Document      │───▶│   Processing    │───▶│   Delivery      │
│   Ingestion     │    │   Pipeline      │    │   & Storage     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
    FastAPI + CLI        OCR + Conversion        S3/SFTP/Shopify
    Background Jobs      Template Engine         Bates Numbering
    YAML Routing         BaaS Integration        Audit Logging
```

## 🔧 Installation

### Docker (Recommended)

```bash
docker-compose up -d
```

### Local Development

```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y tesseract-ocr poppler-utils wkhtmltopdf

# Install Python dependencies
pip install -r requirements.txt

# Initialize database
alembic upgrade head

# Start services
redis-server &
celery -A app.worker worker --loglevel=info &
python -m app.main
```

## 🌐 API Endpoints

### Document Processing
- `POST /api/v1/documents` - Upload document
- `POST /api/v1/jobs/{job_id}/run` - Start processing
- `GET /api/v1/jobs/{job_id}` - Get job status
- `GET /api/v1/outputs/{doc_id}` - Download results

### Connectors  
- `POST /api/v1/connectors/shopify/upload` - Upload to Shopify
- `POST /api/v1/connectors/s3/push` - Push to S3
- `POST /api/v1/connectors/sftp/push` - Upload via SFTP

### BaaS Integration
- `POST /api/v1/baas/webhook` - Webhook endpoint

## 🛠️ CLI Commands

```bash
# Ingest documents
python cli.py ingest /path/to/documents

# Process jobs
python cli.py run JOB_ID
python cli.py run --folder /path/to/jobs

# Test routing
python cli.py route document.pdf --dry-run

# Apply Bates numbering
python cli.py bates document.pdf --start 1000 --prefix "LEGAL"

# Generate reports
python cli.py report data.csv template.docx

# Deliver documents
python cli.py deliver document.pdf --target s3://bucket/prefix
```

## ⚙️ Configuration

Copy `.env.example` to `.env` and configure:

### Required
- `DATABASE_URL` - Database connection
- `REDIS_URL` - Redis connection
- `SECRET_KEY` - JWT secret

### Optional BaaS Integration
- `LV_BAAS_API_KEY` - Lid Vizion API key
- `LV_BAAS_WORKFLOW_ID` - Workflow identifier

### Connectors
- `SHOPIFY_SHOP` & `SHOPIFY_ACCESS_TOKEN`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`
- `SFTP_HOST`, `SFTP_USER`, `SFTP_PASSWORD`

## 📁 Routing Rules

Configure document routing with YAML:

```yaml
# rules/routing.yaml
rules:
  - name: "Invoice Processing"
    conditions:
      filename_regex: ".*invoice.*"
      keywords: ["invoice", "billing", "payment"]
    actions:
      destination: "s3://invoices/{date_yyyy_mm_dd}/"
      rename_template: "INV_{date_yyyy_mm_dd}_{counter:6}"
      bates_prefix: "INV"
```

## 🔍 Document Templates

### DOCX Templates (docxtpl)
```python
# templates/invoice.docx with placeholders
{{ company_name }}
{{ invoice_number }}
{% for item in items %}
- {{ item.description }}: ${{ item.amount }}
{% endfor %}
```

### HTML Templates (Jinja2)
```html
<!-- templates/report.html -->
<html>
<body>
  <h1>{{ report_title }}</h1>
  <table>
    {% for row in data %}
    <tr><td>{{ row.field1 }}</td><td>{{ row.field2 }}</td></tr>
    {% endfor %}
  </table>
</body>
</html>
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# Test with coverage
pytest --cov=app --cov-report=html
```

## 📦 Sample Data

The `data/samples/` directory contains:
- Scanned invoice PDF
- Bank statement image
- Multi-page form PDF
- Receipt photos
- Expected output examples

## 🐳 Docker Services

- **api**: FastAPI application (port 8000)
- **worker**: Celery background processor
- **redis**: Task queue and caching
- **db**: PostgreSQL database (optional, defaults to SQLite)

## 🔒 Security Features

- File type validation and size limits
- PII masking in logs
- Secure file quarantine
- Audit trail for all operations
- API authentication (optional)

## 📊 Monitoring & Logging

- Structured JSON logging
- Job progress tracking  
- Error handling and recovery
- Performance metrics
- Audit trail for compliance

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Run tests: `make test`
4. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🆘 Support

- Check logs: `docker-compose logs api worker`
- Test OCR: `python -c "import pytesseract; print(pytesseract.get_tesseract_version())"`
- Validate routing: `python cli.py route --test`

---

Built with Python 3.11, FastAPI, and modern document processing tools.