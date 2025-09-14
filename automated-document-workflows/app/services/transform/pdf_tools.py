"""
PDF processing and manipulation tools.
"""

import os
import tempfile
import subprocess
from typing import Optional, Dict, Any, List
from pathlib import Path

import fitz  # PyMuPDF
import pikepdf
from PIL import Image

from app.utils.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PDFProcessor:
    """PDF processing and manipulation utilities."""
    
    def __init__(self):
        pass
    
    def make_searchable(
        self,
        input_path: str,
        output_dir: str,
        language: str = "eng"
    ) -> Optional[str]:
        """
        Convert a PDF to searchable PDF with OCR text layer.
        
        Args:
            input_path: Path to input PDF
            output_dir: Directory for output file
            language: OCR language
            
        Returns:
            Path to searchable PDF or None if failed
        """
        
        if not Path(input_path).exists():
            raise FileNotFoundError(f"Input PDF not found: {input_path}")
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate output filename
        input_name = Path(input_path).stem
        output_path = os.path.join(output_dir, f"{input_name}_searchable.pdf")
        
        try:
            # Check if PDF already has text
            if self._has_text_content(input_path):
                logger.info(f"PDF already searchable: {input_path}")
                # Just copy the file
                import shutil
                shutil.copy2(input_path, output_path)
                return output_path
            
            # Use ocrmypdf to create searchable PDF
            cmd = [
                "ocrmypdf",
                "--language", language,
                "--optimize", "1",
                "--deskew",
                "--clean",
                "--rotate-pages",
                input_path,
                output_path
            ]
            
            logger.info(f"Creating searchable PDF: {output_path}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.ocrmypdf_timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Searchable PDF created: {output_path}")
                return output_path
            else:
                error_msg = result.stderr or "ocrmypdf failed"
                logger.error(f"ocrmypdf error: {error_msg}")
                
                # Fallback: try without some options
                return self._create_searchable_fallback(input_path, output_path, language)
                
        except subprocess.TimeoutExpired:
            logger.error("ocrmypdf timed out")
            return None
        except Exception as e:
            logger.error(f"Searchable PDF creation failed: {e}")
            return None
    
    def _create_searchable_fallback(
        self,
        input_path: str,
        output_path: str,
        language: str
    ) -> Optional[str]:
        """Fallback method for creating searchable PDF."""
        
        try:
            # Try simpler ocrmypdf command
            cmd = [
                "ocrmypdf",
                "--language", language,
                "--force-ocr",
                input_path,
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                return output_path
            else:
                logger.warning("Fallback ocrmypdf also failed")
                return None
                
        except Exception as e:
            logger.warning(f"Fallback searchable PDF creation failed: {e}")
            return None
    
    def _has_text_content(self, pdf_path: str, min_text_length: int = 100) -> bool:
        """Check if PDF has substantial text content."""
        
        try:
            doc = fitz.open(pdf_path)
            total_text = ""
            
            # Check first few pages for text
            pages_to_check = min(3, len(doc))
            
            for page_num in range(pages_to_check):
                page = doc[page_num]
                text = page.get_text().strip()
                total_text += text
                
                # Early exit if we have enough text
                if len(total_text) >= min_text_length:
                    doc.close()
                    return True
            
            doc.close()
            
            return len(total_text.strip()) >= min_text_length
            
        except Exception as e:
            logger.warning(f"Error checking PDF text content: {e}")
            return False
    
    def extract_metadata(self, pdf_path: str) -> Dict[str, Any]:
        """Extract metadata from PDF."""
        
        try:
            doc = fitz.open(pdf_path)
            metadata = doc.metadata
            
            result = {
                "title": metadata.get("title", ""),
                "author": metadata.get("author", ""),
                "subject": metadata.get("subject", ""),
                "creator": metadata.get("creator", ""),
                "producer": metadata.get("producer", ""),
                "creation_date": metadata.get("creationDate", ""),
                "modification_date": metadata.get("modDate", ""),
                "page_count": len(doc),
                "file_size": os.path.getsize(pdf_path),
            }
            
            # Get page dimensions
            if len(doc) > 0:
                first_page = doc[0]
                rect = first_page.rect
                result["page_width"] = rect.width
                result["page_height"] = rect.height
            
            doc.close()
            
            return result
            
        except Exception as e:
            logger.error(f"PDF metadata extraction failed: {e}")
            return {}
    
    def split_pdf(
        self,
        input_path: str,
        output_dir: str,
        page_ranges: Optional[List[tuple]] = None
    ) -> List[str]:
        """
        Split PDF into separate files.
        
        Args:
            input_path: Path to input PDF
            output_dir: Directory for output files
            page_ranges: List of (start, end) tuples for page ranges
                        If None, split into individual pages
            
        Returns:
            List of created file paths
        """
        
        if not Path(input_path).exists():
            raise FileNotFoundError(f"Input PDF not found: {input_path}")
        
        os.makedirs(output_dir, exist_ok=True)
        created_files = []
        
        try:
            doc = fitz.open(input_path)
            input_name = Path(input_path).stem
            
            if page_ranges is None:
                # Split into individual pages
                page_ranges = [(i, i) for i in range(len(doc))]
            
            for i, (start, end) in enumerate(page_ranges):
                # Create new PDF for this range
                new_doc = fitz.open()
                
                for page_num in range(start, min(end + 1, len(doc))):
                    new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                
                # Save split PDF
                if start == end:
                    output_path = os.path.join(output_dir, f"{input_name}_page_{start + 1}.pdf")
                else:
                    output_path = os.path.join(output_dir, f"{input_name}_pages_{start + 1}-{end + 1}.pdf")
                
                new_doc.save(output_path)
                new_doc.close()
                
                created_files.append(output_path)
                logger.debug(f"Created split PDF: {output_path}")
            
            doc.close()
            
            logger.info(f"Split PDF into {len(created_files)} files")
            return created_files
            
        except Exception as e:
            logger.error(f"PDF splitting failed: {e}")
            
            # Clean up any created files on failure
            for file_path in created_files:
                try:
                    os.remove(file_path)
                except:
                    pass
            
            raise e
    
    def merge_pdfs(
        self,
        input_paths: List[str],
        output_path: str,
        bookmarks: Optional[List[str]] = None
    ) -> str:
        """
        Merge multiple PDFs into one.
        
        Args:
            input_paths: List of PDF file paths to merge
            output_path: Path for merged output PDF
            bookmarks: Optional list of bookmark names for each PDF
            
        Returns:
            Path to merged PDF
        """
        
        if not input_paths:
            raise ValueError("No input PDFs provided")
        
        # Verify all input files exist
        for path in input_paths:
            if not Path(path).exists():
                raise FileNotFoundError(f"Input PDF not found: {path}")
        
        os.makedirs(Path(output_path).parent, exist_ok=True)
        
        try:
            merged_doc = fitz.open()
            
            for i, pdf_path in enumerate(input_paths):
                doc = fitz.open(pdf_path)
                
                # Add bookmark if provided
                if bookmarks and i < len(bookmarks):
                    bookmark_title = bookmarks[i]
                    page_num = len(merged_doc)
                    merged_doc.set_toc_item(page_num, bookmark_title, 1)
                
                # Insert all pages from this PDF
                merged_doc.insert_pdf(doc)
                doc.close()
            
            # Save merged PDF
            merged_doc.save(output_path)
            merged_doc.close()
            
            logger.info(f"Merged {len(input_paths)} PDFs into: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"PDF merging failed: {e}")
            raise e
    
    def optimize_pdf(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        compression_level: int = 1
    ) -> str:
        """
        Optimize PDF for smaller file size.
        
        Args:
            input_path: Path to input PDF
            output_path: Path for optimized PDF (overwrites input if None)
            compression_level: 0-3, higher = more compression
            
        Returns:
            Path to optimized PDF
        """
        
        if not Path(input_path).exists():
            raise FileNotFoundError(f"Input PDF not found: {input_path}")
        
        if output_path is None:
            output_path = input_path
        else:
            os.makedirs(Path(output_path).parent, exist_ok=True)
        
        try:
            # Use pikepdf for optimization
            with pikepdf.open(input_path) as pdf:
                # Remove unused objects
                pdf.remove_unreferenced_resources()
                
                # Optimize images if compression level > 0
                if compression_level > 0:
                    for page in pdf.pages:
                        for image in page.images:
                            try:
                                # This would need more sophisticated image compression
                                pass
                            except:
                                continue
                
                # Save optimized PDF
                save_kwargs = {}
                if compression_level >= 2:
                    save_kwargs['compress_streams'] = True
                    save_kwargs['object_stream_mode'] = pikepdf.ObjectStreamMode.generate
                
                pdf.save(output_path, **save_kwargs)
            
            # Get size reduction info
            original_size = os.path.getsize(input_path)
            optimized_size = os.path.getsize(output_path)
            reduction_percent = ((original_size - optimized_size) / original_size) * 100
            
            logger.info(f"PDF optimized: {reduction_percent:.1f}% size reduction")
            
            return output_path
            
        except Exception as e:
            logger.error(f"PDF optimization failed: {e}")
            raise e
    
    def add_watermark(
        self,
        input_path: str,
        watermark_text: str,
        output_path: Optional[str] = None,
        position: str = "center",
        opacity: float = 0.3
    ) -> str:
        """
        Add text watermark to PDF.
        
        Args:
            input_path: Path to input PDF
            watermark_text: Text to use as watermark
            output_path: Path for watermarked PDF
            position: Watermark position (center, top_left, etc.)
            opacity: Watermark opacity (0.0-1.0)
            
        Returns:
            Path to watermarked PDF
        """
        
        if not Path(input_path).exists():
            raise FileNotFoundError(f"Input PDF not found: {input_path}")
        
        if output_path is None:
            input_name = Path(input_path).stem
            output_path = str(Path(input_path).parent / f"{input_name}_watermarked.pdf")
        else:
            os.makedirs(Path(output_path).parent, exist_ok=True)
        
        try:
            doc = fitz.open(input_path)
            
            for page in doc:
                rect = page.rect
                
                # Calculate watermark position
                if position == "center":
                    point = fitz.Point(rect.width / 2, rect.height / 2)
                elif position == "top_left":
                    point = fitz.Point(50, 50)
                elif position == "top_right":
                    point = fitz.Point(rect.width - 100, 50)
                elif position == "bottom_left":
                    point = fitz.Point(50, rect.height - 50)
                elif position == "bottom_right":
                    point = fitz.Point(rect.width - 100, rect.height - 50)
                else:
                    point = fitz.Point(rect.width / 2, rect.height / 2)
                
                # Add watermark text
                page.insert_text(
                    point,
                    watermark_text,
                    fontsize=36,
                    color=(0.5, 0.5, 0.5),  # Gray color
                    rotate=45,  # 45-degree rotation
                    overlay=True
                )
            
            # Save watermarked PDF
            doc.save(output_path)
            doc.close()
            
            logger.info(f"Watermark added to PDF: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"PDF watermarking failed: {e}")
            raise e
    
    def extract_images(
        self,
        input_path: str,
        output_dir: str,
        image_format: str = "PNG"
    ) -> List[str]:
        """
        Extract all images from PDF.
        
        Args:
            input_path: Path to input PDF
            output_dir: Directory for extracted images
            image_format: Image format (PNG, JPEG)
            
        Returns:
            List of extracted image file paths
        """
        
        if not Path(input_path).exists():
            raise FileNotFoundError(f"Input PDF not found: {input_path}")
        
        os.makedirs(output_dir, exist_ok=True)
        extracted_images = []
        
        try:
            doc = fitz.open(input_path)
            input_name = Path(input_path).stem
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)
                    
                    # Skip CMYK images (not supported by PIL)
                    if pix.n - pix.alpha < 4:
                        # Convert to PNG/JPEG
                        image_filename = f"{input_name}_page{page_num + 1}_img{img_index + 1}.{image_format.lower()}"
                        image_path = os.path.join(output_dir, image_filename)
                        
                        if image_format.upper() == "PNG":
                            pix.save(image_path)
                        else:
                            # For JPEG, convert to RGB first
                            if pix.alpha:
                                pix = fitz.Pixmap(fitz.csRGB, pix)
                            pix.save(image_path)
                        
                        extracted_images.append(image_path)
                    
                    pix = None  # Free memory
            
            doc.close()
            
            logger.info(f"Extracted {len(extracted_images)} images from PDF")
            return extracted_images
            
        except Exception as e:
            logger.error(f"PDF image extraction failed: {e}")
            raise e