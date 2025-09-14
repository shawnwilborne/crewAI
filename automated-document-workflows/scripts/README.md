# Utility Scripts

This directory contains utility scripts for batch operations and desktop integration.

## Windows PowerShell Scripts

### AddBates.ps1
Adds Bates numbering to PDF files using COM Office integration.

```powershell
# Add Bates numbering to single file
.\AddBates.ps1 -FilePath "document.pdf" -StartNumber 1000 -Prefix "LEGAL"

# Batch add Bates numbering to folder
.\AddBates.ps1 -FolderPath "C:\Documents" -StartNumber 1 -Prefix "CASE001"
```

### BatchConvert.ps1
Batch converts Office documents using COM automation.

```powershell
# Convert all Word docs to PDF
.\BatchConvert.ps1 -SourceFolder "C:\Documents" -OutputFolder "C:\PDFs" -Format PDF

# Convert with OCR
.\BatchConvert.ps1 -SourceFolder "C:\Scanned" -OutputFolder "C:\Processed" -OCR
```

## Linux/Mac Shell Scripts

### batch_convert.sh
Cross-platform batch conversion using system tools.

```bash
# Convert documents in folder
./batch_convert.sh /path/to/documents /path/to/output

# Convert with specific options
./batch_convert.sh /path/to/documents /path/to/output --ocr --format pdf
```

## Usage Notes

- PowerShell scripts require Office applications to be installed
- Linux scripts use LibreOffice and system tools
- All scripts support dry-run mode for testing
- Logging is enabled by default for audit trails

## Integration with Main System

These scripts can be used alongside the main API/CLI system:

1. **Pre-processing**: Use scripts to prepare documents before ingestion
2. **Post-processing**: Apply additional transformations to outputs  
3. **Batch operations**: Process large document sets efficiently
4. **Desktop integration**: Provide right-click menu options for users