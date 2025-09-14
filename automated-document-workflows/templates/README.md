# Document Templates

This directory contains document templates for various output formats.

## Template Types

### DOCX Templates (using docxtpl)
- Use `{{ variable }}` for simple variable substitution
- Use `{% for item in items %}` for loops
- Use `{% if condition %}` for conditional content
- Templates can include tables, images, and complex formatting

### HTML Templates (using Jinja2)
- Full Jinja2 template syntax supported
- Can be converted to PDF using WeasyPrint
- Supports CSS styling and responsive design
- Good for reports and web-ready documents

## Available Templates

1. **invoice.docx** - Business invoice template
2. **report.html** - Business report template  
3. **letter.docx** - Formal business letter template
4. **statement.html** - Financial statement template
5. **contract.docx** - Basic contract template

## Template Variables

Common variables available in templates:
- `{{ company_name }}` - Company name
- `{{ date }}` - Current date
- `{{ document_title }}` - Document title
- `{{ recipient_name }}` - Recipient name
- `{{ items }}` - List of items/data rows
- `{{ total_amount }}` - Total amount (for financial docs)
- `{{ custom_fields }}` - Dictionary of custom fields

## Usage

Templates are automatically discovered and can be used in:
- API endpoints (`POST /api/v1/documents/{id}/generate`)
- CLI commands (`cli.py report data.csv template.docx`)
- Pipeline configuration (set `apply_template: true`)

## Creating Custom Templates

1. Create a new `.docx` or `.html` file in this directory
2. Use appropriate template syntax for the format
3. Test with sample data using the CLI or API
4. Document required variables in comments