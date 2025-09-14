# Sample Documents

This directory contains sample documents for testing the automated document processing workflows.

## Sample Files

### Test Documents
- **scanned_invoice.pdf** - Scanned invoice requiring OCR processing
- **bank_statement.png** - Bank statement image for OCR testing
- **contract_form.pdf** - Multi-page contract document
- **receipt.jpg** - Receipt photo for processing
- **business_report.docx** - Text-based business report

### Expected Outputs
The `expected_outputs/` directory contains the expected results for each sample document:
- OCR text extraction results
- Converted DOCX files
- Searchable PDF versions
- Routing decisions
- Renamed file examples

## Usage

### CLI Testing
```bash
# Ingest all sample documents
python cli.py ingest data/samples/ --recursive --auto-process

# Test specific document
python cli.py ingest data/samples/scanned_invoice.pdf --auto-process

# Test routing rules
python cli.py route data/samples/scanned_invoice.pdf --dry-run --verbose
```

### API Testing
```bash
# Upload document via API
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -F "file=@data/samples/scanned_invoice.pdf" \
  -F "auto_process=true"

# Check processing status
curl "http://localhost:8000/api/v1/jobs/{job_id}"
```

## Document Types Covered

1. **Invoices** - Testing invoice detection and routing rules
2. **Bank Statements** - Financial document processing
3. **Contracts** - Legal document handling with Bates numbering
4. **Receipts** - Expense document processing
5. **Reports** - Business document template generation

## Testing Scenarios

### OCR Testing
- Scanned documents with various quality levels
- Multi-language documents
- Documents with tables and complex layouts
- Handwritten text recognition

### Routing Testing  
- Documents matching different rule conditions
- Priority rule evaluation
- Template-based renaming
- Multiple destination routing

### Integration Testing
- BaaS vs local processing comparison
- End-to-end workflow validation
- Error handling and recovery
- Performance benchmarking

## Adding New Samples

1. Add new document files to this directory
2. Create corresponding expected outputs in `expected_outputs/`
3. Update test cases to include the new samples
4. Document any special processing requirements