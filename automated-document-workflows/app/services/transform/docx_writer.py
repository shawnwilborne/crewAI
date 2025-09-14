"""
DOCX document creation and conversion utilities.
"""

import os
from typing import Optional, Dict, Any, List
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docxtpl import DocxTemplate

from app.utils.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DOCXWriter:
    """DOCX document creation and conversion utilities."""
    
    def __init__(self):
        pass
    
    def convert_from_document(
        self,
        input_path: str,
        extracted_text: Optional[str] = None,
        output_dir: str = None,
        preserve_formatting: bool = True
    ) -> Optional[str]:
        """
        Convert a document to DOCX format.
        
        Args:
            input_path: Path to input document
            extracted_text: Pre-extracted text content
            output_dir: Output directory
            preserve_formatting: Whether to attempt to preserve formatting
            
        Returns:
            Path to created DOCX file or None if failed
        """
        
        if output_dir is None:
            output_dir = settings.output_dir
        
        os.makedirs(output_dir, exist_ok=True)
        
        input_name = Path(input_path).stem
        output_path = os.path.join(output_dir, f"{input_name}.docx")
        
        try:
            # Create new document
            doc = Document()
            
            # Set document properties
            doc.core_properties.title = input_name
            doc.core_properties.author = "Automated Document Workflows"
            
            if extracted_text:
                # Use provided text
                self._add_text_to_document(doc, extracted_text, preserve_formatting)
            else:
                # Try to extract text from source
                text = self._extract_text_from_file(input_path)
                if text:
                    self._add_text_to_document(doc, text, preserve_formatting)
                else:
                    # Add placeholder content
                    self._add_placeholder_content(doc, input_name)
            
            # Save document
            doc.save(output_path)
            
            logger.info(f"DOCX created: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"DOCX conversion failed: {e}")
            return None
    
    def create_from_template(
        self,
        template_path: str,
        data: Dict[str, Any],
        output_path: str
    ) -> str:
        """
        Create DOCX from template with data substitution.
        
        Args:
            template_path: Path to DOCX template
            data: Data dictionary for template substitution
            output_path: Path for output DOCX
            
        Returns:
            Path to created DOCX file
        """
        
        if not Path(template_path).exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        
        os.makedirs(Path(output_path).parent, exist_ok=True)
        
        try:
            # Load template
            doc = DocxTemplate(template_path)
            
            # Render with data
            doc.render(data)
            
            # Save document
            doc.save(output_path)
            
            logger.info(f"DOCX created from template: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Template DOCX creation failed: {e}")
            raise e
    
    def create_report(
        self,
        title: str,
        content_sections: List[Dict[str, Any]],
        output_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a formatted report DOCX.
        
        Args:
            title: Report title
            content_sections: List of content sections
            output_path: Path for output DOCX
            metadata: Optional metadata to include
            
        Returns:
            Path to created DOCX file
        """
        
        os.makedirs(Path(output_path).parent, exist_ok=True)
        
        try:
            # Create new document
            doc = Document()
            
            # Set document properties
            doc.core_properties.title = title
            doc.core_properties.author = "Automated Document Workflows"
            
            if metadata:
                doc.core_properties.subject = metadata.get("subject", "")
                doc.core_properties.keywords = metadata.get("keywords", "")
            
            # Add title
            title_paragraph = doc.add_heading(title, level=1)
            title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # Add metadata section if provided
            if metadata:
                doc.add_heading("Document Information", level=2)
                
                info_table = doc.add_table(rows=0, cols=2)
                info_table.style = 'Table Grid'
                
                for key, value in metadata.items():
                    if key not in ['subject', 'keywords']:  # Skip already used fields
                        row_cells = info_table.add_row().cells
                        row_cells[0].text = str(key).replace('_', ' ').title()
                        row_cells[1].text = str(value)
                
                doc.add_paragraph()  # Add space
            
            # Add content sections
            for section in content_sections:
                section_title = section.get('title', 'Section')
                section_content = section.get('content', '')
                section_type = section.get('type', 'paragraph')
                
                # Add section heading
                if section_title:
                    doc.add_heading(section_title, level=2)
                
                # Add content based on type
                if section_type == 'paragraph':
                    self._add_formatted_text(doc, section_content)
                elif section_type == 'table' and isinstance(section_content, list):
                    self._add_table_content(doc, section_content)
                elif section_type == 'list' and isinstance(section_content, list):
                    self._add_list_content(doc, section_content)
                else:
                    # Default to paragraph
                    doc.add_paragraph(str(section_content))
            
            # Save document
            doc.save(output_path)
            
            logger.info(f"Report DOCX created: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Report DOCX creation failed: {e}")
            raise e
    
    def _add_text_to_document(
        self,
        doc: Document,
        text: str,
        preserve_formatting: bool = True
    ):
        """Add text content to document with optional formatting preservation."""
        
        if preserve_formatting:
            # Try to preserve paragraph structure
            paragraphs = text.split('\n\n')
            
            for paragraph_text in paragraphs:
                paragraph_text = paragraph_text.strip()
                if paragraph_text:
                    # Check if this looks like a heading
                    if self._looks_like_heading(paragraph_text):
                        doc.add_heading(paragraph_text, level=2)
                    else:
                        paragraph = doc.add_paragraph(paragraph_text)
                        # Set reasonable formatting
                        paragraph.style.font.name = 'Calibri'
                        paragraph.style.font.size = Pt(11)
        else:
            # Add as single paragraph
            paragraph = doc.add_paragraph(text)
            paragraph.style.font.name = 'Calibri'
            paragraph.style.font.size = Pt(11)
    
    def _add_formatted_text(self, doc: Document, text: str):
        """Add formatted text content to document."""
        
        # Split into paragraphs
        paragraphs = text.split('\n\n')
        
        for paragraph_text in paragraphs:
            paragraph_text = paragraph_text.strip()
            if paragraph_text:
                paragraph = doc.add_paragraph(paragraph_text)
                paragraph.style.font.name = 'Calibri'
                paragraph.style.font.size = Pt(11)
    
    def _add_table_content(self, doc: Document, table_data: List[List[str]]):
        """Add table content to document."""
        
        if not table_data:
            return
        
        # Create table
        table = doc.add_table(rows=1, cols=len(table_data[0]))
        table.style = 'Table Grid'
        
        # Add header row
        header_cells = table.rows[0].cells
        for i, header in enumerate(table_data[0]):
            header_cells[i].text = str(header)
            # Make header bold
            header_cells[i].paragraphs[0].runs[0].bold = True
        
        # Add data rows
        for row_data in table_data[1:]:
            row_cells = table.add_row().cells
            for i, cell_data in enumerate(row_data):
                if i < len(row_cells):
                    row_cells[i].text = str(cell_data)
    
    def _add_list_content(self, doc: Document, list_data: List[str]):
        """Add list content to document."""
        
        for item in list_data:
            doc.add_paragraph(str(item), style='List Bullet')
    
    def _looks_like_heading(self, text: str) -> bool:
        """Determine if text looks like a heading."""
        
        # Simple heuristics for heading detection
        if len(text) < 5:
            return False
        
        if len(text) > 100:
            return False
        
        # Check for common heading patterns
        heading_patterns = [
            text.isupper(),  # ALL CAPS
            text.istitle(),  # Title Case
            text.endswith(':'),  # Ends with colon
            any(text.startswith(prefix) for prefix in ['Chapter', 'Section', 'Part']),
        ]
        
        return any(heading_patterns)
    
    def _extract_text_from_file(self, file_path: str) -> Optional[str]:
        """Extract text from various file formats."""
        
        file_extension = Path(file_path).suffix.lower()
        
        try:
            if file_extension == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            elif file_extension == '.docx':
                doc = Document(file_path)
                paragraphs = [p.text for p in doc.paragraphs]
                return '\n'.join(paragraphs)
            # Add more formats as needed
            else:
                logger.warning(f"Text extraction not supported for: {file_extension}")
                return None
                
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            return None
    
    def _add_placeholder_content(self, doc: Document, filename: str):
        """Add placeholder content when no text is available."""
        
        doc.add_heading("Document Conversion", level=1)
        
        doc.add_paragraph(
            f"This document was automatically converted from: {filename}"
        )
        
        doc.add_paragraph(
            "The original document could not be processed for text extraction. "
            "This may be because the document is image-based and requires OCR processing, "
            "or the document format is not fully supported."
        )
        
        doc.add_paragraph(
            "To improve text extraction, consider:"
        )
        
        doc.add_paragraph("• Enabling OCR processing for image-based documents", style='List Bullet')
        doc.add_paragraph("• Using higher quality source documents", style='List Bullet')
        doc.add_paragraph("• Converting source documents to text-based formats", style='List Bullet')