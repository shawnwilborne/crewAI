"""
Local OCR processing using Tesseract and ocrmypdf.
"""

import os
import tempfile
import subprocess
from typing import Dict, Any, List, Optional
from pathlib import Path

import pytesseract
import fitz  # PyMuPDF
from PIL import Image

from app.utils.settings import settings
from app.utils.logging import get_logger
from app.utils.image_preprocess import preprocess_image_for_ocr, extract_image_from_pdf

logger = get_logger(__name__)


class LocalOCRProcessor:
    """Local OCR processing using Tesseract and related tools."""
    
    def __init__(self):
        # Set Tesseract command path if configured
        if settings.tesseract_cmd and settings.tesseract_cmd != "tesseract":
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    
    def process_document(
        self,
        file_path: str,
        language: str = "eng",
        dpi: int = 300,
        preprocess: bool = True
    ) -> Dict[str, Any]:
        """
        Process a document with OCR to extract text and metadata.
        
        Args:
            file_path: Path to document file
            language: Tesseract language code
            dpi: DPI for image rendering
            preprocess: Whether to preprocess images for better OCR
            
        Returns:
            OCR processing results
        """
        
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Document not found: {file_path}")
        
        file_extension = Path(file_path).suffix.lower()
        
        try:
            if file_extension == '.pdf':
                return self._process_pdf(file_path, language, dpi, preprocess)
            elif file_extension in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
                return self._process_image(file_path, language, preprocess)
            else:
                raise ValueError(f"Unsupported file format: {file_extension}")
                
        except Exception as e:
            logger.error(f"OCR processing failed for {file_path}: {e}")
            raise e
    
    def _process_pdf(
        self,
        pdf_path: str,
        language: str,
        dpi: int,
        preprocess: bool
    ) -> Dict[str, Any]:
        """Process PDF document with OCR."""
        
        logger.info(f"Processing PDF with OCR: {pdf_path}")
        
        try:
            # First, try to extract existing text
            existing_text = self._extract_pdf_text(pdf_path)
            
            if existing_text and len(existing_text.strip()) > 50:
                # PDF already has substantial text, no OCR needed
                logger.info("PDF already contains text, skipping OCR")
                
                return {
                    "engine": "pdf_text_extraction",
                    "extracted_text": existing_text,
                    "page_count": self._get_pdf_page_count(pdf_path),
                    "has_existing_text": True,
                    "confidence_score": 1.0,  # Text extraction is 100% accurate
                    "language": self._detect_language(existing_text),
                    "processing_time_ms": 0,  # Minimal processing time
                }
            
            # PDF needs OCR - use ocrmypdf for best results
            return self._ocr_pdf_with_ocrmypdf(pdf_path, language, dpi)
            
        except Exception as e:
            logger.warning(f"OCR PDF processing failed, trying image extraction: {e}")
            # Fallback to extracting images and OCR them individually
            return self._ocr_pdf_by_images(pdf_path, language, dpi, preprocess)
    
    def _process_image(
        self,
        image_path: str,
        language: str,
        preprocess: bool
    ) -> Dict[str, Any]:
        """Process image file with OCR."""
        
        logger.info(f"Processing image with OCR: {image_path}")
        
        try:
            # Preprocess image if requested
            processed_image_path = image_path
            if preprocess:
                processed_image_path = preprocess_image_for_ocr(image_path)
            
            # Perform OCR
            result = self._tesseract_ocr(processed_image_path, language)
            
            # Clean up preprocessed image if it was created
            if preprocess and processed_image_path != image_path:
                try:
                    os.remove(processed_image_path)
                except:
                    pass
            
            return {
                "engine": "tesseract",
                "extracted_text": result["text"],
                "confidence_score": result["confidence"],
                "language": language,
                "page_count": 1,
                "has_existing_text": False,
                "processing_time_ms": result.get("processing_time_ms", 0),
                "image_preprocessed": preprocess,
            }
            
        except Exception as e:
            logger.error(f"Image OCR failed: {e}")
            raise e
    
    def _extract_pdf_text(self, pdf_path: str) -> str:
        """Extract existing text from PDF."""
        
        try:
            doc = fitz.open(pdf_path)
            text_parts = []
            
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)
            
            doc.close()
            
            return "\n".join(text_parts)
            
        except Exception as e:
            logger.warning(f"PDF text extraction failed: {e}")
            return ""
    
    def _get_pdf_page_count(self, pdf_path: str) -> int:
        """Get number of pages in PDF."""
        
        try:
            doc = fitz.open(pdf_path)
            page_count = len(doc)
            doc.close()
            return page_count
        except Exception as e:
            logger.warning(f"Could not get PDF page count: {e}")
            return 0
    
    def _ocr_pdf_with_ocrmypdf(
        self,
        pdf_path: str,
        language: str,
        dpi: int
    ) -> Dict[str, Any]:
        """Use ocrmypdf to OCR a PDF document."""
        
        try:
            # Create temporary output file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_output:
                output_path = temp_output.name
            
            # Build ocrmypdf command
            cmd = [
                "ocrmypdf",
                "--language", language,
                "--deskew",
                "--clean",
                "--force-ocr",  # OCR even if text is present
                "--output-type", "pdf",
                "--optimize", "1",
                pdf_path,
                output_path
            ]
            
            # Add DPI setting if not default
            if dpi != 300:
                cmd.extend(["--pdfa-image-compression", "auto"])
            
            logger.debug(f"Running ocrmypdf: {' '.join(cmd)}")
            
            # Execute ocrmypdf
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.ocrmypdf_timeout
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or "ocrmypdf failed"
                logger.error(f"ocrmypdf error: {error_msg}")
                raise Exception(f"ocrmypdf failed: {error_msg}")
            
            # Extract text from OCR'd PDF
            ocr_text = self._extract_pdf_text(output_path)
            
            # Clean up temporary file
            try:
                os.remove(output_path)
            except:
                pass
            
            return {
                "engine": "ocrmypdf",
                "extracted_text": ocr_text,
                "page_count": self._get_pdf_page_count(pdf_path),
                "has_existing_text": False,
                "confidence_score": self._estimate_ocr_confidence(ocr_text),
                "language": language,
                "processing_time_ms": 0,  # ocrmypdf doesn't provide timing
            }
            
        except subprocess.TimeoutExpired:
            logger.error("ocrmypdf timed out")
            raise Exception("OCR processing timed out")
        except Exception as e:
            logger.error(f"ocrmypdf processing failed: {e}")
            raise e
    
    def _ocr_pdf_by_images(
        self,
        pdf_path: str,
        language: str,
        dpi: int,
        preprocess: bool
    ) -> Dict[str, Any]:
        """OCR PDF by extracting images from each page."""
        
        logger.info("OCR PDF by extracting and processing individual pages")
        
        try:
            doc = fitz.open(pdf_path)
            page_texts = []
            total_confidence = 0
            processed_pages = 0
            
            with tempfile.TemporaryDirectory() as temp_dir:
                for page_num in range(len(doc)):
                    try:
                        # Extract page as image
                        page_image_path = extract_image_from_pdf(
                            pdf_path, 
                            page_num + 1, 
                            temp_dir
                        )
                        
                        # Process image with OCR
                        if preprocess:
                            page_image_path = preprocess_image_for_ocr(page_image_path)
                        
                        # Perform OCR on page
                        ocr_result = self._tesseract_ocr(page_image_path, language)
                        
                        if ocr_result["text"].strip():
                            page_texts.append(ocr_result["text"])
                            total_confidence += ocr_result["confidence"]
                            processed_pages += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to OCR page {page_num + 1}: {e}")
                        continue
            
            doc.close()
            
            # Combine results
            full_text = "\n\n".join(page_texts)
            avg_confidence = total_confidence / processed_pages if processed_pages > 0 else 0
            
            return {
                "engine": "tesseract_pages",
                "extracted_text": full_text,
                "page_count": len(doc),
                "processed_pages": processed_pages,
                "has_existing_text": False,
                "confidence_score": avg_confidence / 100,  # Convert to 0-1 scale
                "language": language,
                "processing_time_ms": 0,
                "image_preprocessed": preprocess,
            }
            
        except Exception as e:
            logger.error(f"PDF page-by-page OCR failed: {e}")
            raise e
    
    def _tesseract_ocr(self, image_path: str, language: str) -> Dict[str, Any]:
        """Perform OCR on image using Tesseract."""
        
        try:
            # Configure Tesseract options
            config = r'--oem 3 --psm 6'  # Use LSTM OCR Engine Mode with uniform text block
            
            # Extract text
            text = pytesseract.image_to_string(
                Image.open(image_path),
                lang=language,
                config=config
            )
            
            # Get confidence data
            data = pytesseract.image_to_data(
                Image.open(image_path),
                lang=language,
                config=config,
                output_type=pytesseract.Output.DICT
            )
            
            # Calculate average confidence
            confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            return {
                "text": text,
                "confidence": avg_confidence,
                "word_count": len(text.split()),
                "character_count": len(text),
            }
            
        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            raise e
    
    def _detect_language(self, text: str) -> str:
        """Detect language of extracted text."""
        
        try:
            # Simple language detection based on common words
            # This could be improved with a proper language detection library
            
            if not text or len(text.strip()) < 10:
                return "unknown"
            
            # Common English words
            english_words = {'the', 'and', 'is', 'in', 'to', 'of', 'a', 'for', 'as', 'with'}
            # Common Spanish words
            spanish_words = {'el', 'la', 'de', 'que', 'y', 'en', 'un', 'es', 'se', 'no'}
            # Common French words
            french_words = {'le', 'de', 'et', 'à', 'un', 'il', 'être', 'et', 'en', 'avoir'}
            # Common German words
            german_words = {'der', 'die', 'und', 'in', 'den', 'von', 'zu', 'das', 'mit', 'sich'}
            
            words = set(text.lower().split())
            
            # Count language matches
            english_count = len(words.intersection(english_words))
            spanish_count = len(words.intersection(spanish_words))
            french_count = len(words.intersection(french_words))
            german_count = len(words.intersection(german_words))
            
            # Return most likely language
            counts = {
                'eng': english_count,
                'spa': spanish_count,
                'fra': french_count,
                'deu': german_count
            }
            
            detected_lang = max(counts, key=counts.get)
            
            # Require at least 2 matches for confidence
            if counts[detected_lang] >= 2:
                return detected_lang
            else:
                return "eng"  # Default to English
                
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return "eng"
    
    def _estimate_ocr_confidence(self, text: str) -> float:
        """Estimate OCR confidence based on text characteristics."""
        
        if not text:
            return 0.0
        
        # Simple heuristic based on text quality indicators
        confidence = 0.5  # Base confidence
        
        # Check for common OCR issues
        total_chars = len(text)
        if total_chars == 0:
            return 0.0
        
        # Count potentially problematic characters
        weird_chars = sum(1 for c in text if ord(c) > 127 and c not in 'àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ')
        weird_ratio = weird_chars / total_chars
        
        # Penalize high weird character ratio
        confidence -= weird_ratio * 0.3
        
        # Count words vs non-word characters
        import re
        words = re.findall(r'\b\w+\b', text)
        if len(words) > 0:
            avg_word_length = sum(len(word) for word in words) / len(words)
            
            # Reasonable word lengths boost confidence
            if 2 <= avg_word_length <= 8:
                confidence += 0.2
            
            # Very short or very long average word lengths reduce confidence
            if avg_word_length < 2 or avg_word_length > 12:
                confidence -= 0.2
        
        # Ensure confidence is between 0 and 1
        return max(0.0, min(1.0, confidence))
    
    def get_available_languages(self) -> List[str]:
        """Get list of available Tesseract languages."""
        
        try:
            return pytesseract.get_languages()
        except Exception as e:
            logger.warning(f"Could not get Tesseract languages: {e}")
            return ["eng"]  # Return default if failed