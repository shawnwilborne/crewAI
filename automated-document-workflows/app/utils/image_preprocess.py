"""
Image preprocessing utilities for document processing.
"""

import os
import tempfile
from typing import Optional, Tuple
from io import BytesIO

import cv2
import numpy as np
from PIL import Image
import fitz  # PyMuPDF

from app.utils.logging import get_logger

logger = get_logger(__name__)


def generate_page_image(
    file_path: str,
    page_number: int,
    width: Optional[int] = None,
    height: Optional[int] = None,
    dpi: int = 150,
    format: str = "PNG"
) -> bytes:
    """Generate an image of a specific page from a PDF or image file."""
    
    try:
        file_extension = os.path.splitext(file_path)[1].lower()
        
        if file_extension == '.pdf':
            return _generate_pdf_page_image(file_path, page_number, width, height, dpi, format)
        elif file_extension in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
            return _generate_image_page(file_path, width, height, format)
        else:
            raise ValueError(f"Unsupported file format: {file_extension}")
            
    except Exception as e:
        logger.error(f"Failed to generate page image: {e}")
        raise


def _generate_pdf_page_image(
    file_path: str,
    page_number: int,
    width: Optional[int],
    height: Optional[int],
    dpi: int,
    format: str
) -> bytes:
    """Generate image from PDF page."""
    
    # Open PDF
    doc = fitz.open(file_path)
    
    if page_number < 1 or page_number > len(doc):
        doc.close()
        raise ValueError(f"Page {page_number} not found in PDF (total pages: {len(doc)})")
    
    # Get page (0-indexed)
    page = doc[page_number - 1]
    
    # Calculate zoom factor based on DPI
    zoom = dpi / 72.0  # PDF default is 72 DPI
    mat = fitz.Matrix(zoom, zoom)
    
    # Render page to pixmap
    pix = page.get_pixmap(matrix=mat)
    
    # Convert to PIL Image
    img_data = pix.tobytes("png")
    image = Image.open(BytesIO(img_data))
    
    doc.close()
    
    # Resize if requested
    if width or height:
        image = _resize_image(image, width, height)
    
    # Convert to bytes
    output = BytesIO()
    image.save(output, format=format)
    
    return output.getvalue()


def _generate_image_page(
    file_path: str,
    width: Optional[int],
    height: Optional[int],
    format: str
) -> bytes:
    """Generate image from image file."""
    
    # Open image
    image = Image.open(file_path)
    
    # Convert to RGB if necessary
    if image.mode != 'RGB' and format == 'JPEG':
        image = image.convert('RGB')
    
    # Resize if requested
    if width or height:
        image = _resize_image(image, width, height)
    
    # Convert to bytes
    output = BytesIO()
    image.save(output, format=format)
    
    return output.getvalue()


def _resize_image(image: Image.Image, width: Optional[int], height: Optional[int]) -> Image.Image:
    """Resize image while maintaining aspect ratio."""
    
    original_width, original_height = image.size
    
    if width and height:
        # Both dimensions specified - use as is (may distort)
        new_size = (width, height)
    elif width:
        # Width specified - calculate height maintaining aspect ratio
        ratio = width / original_width
        new_size = (width, int(original_height * ratio))
    elif height:
        # Height specified - calculate width maintaining aspect ratio
        ratio = height / original_height
        new_size = (int(original_width * ratio), height)
    else:
        # No resize needed
        return image
    
    return image.resize(new_size, Image.Resampling.LANCZOS)


def preprocess_image_for_ocr(image_path: str, output_path: Optional[str] = None) -> str:
    """Preprocess an image to improve OCR accuracy."""
    
    try:
        # Read image
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not read image: {image_path}")
        
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply noise reduction
        denoised = cv2.medianBlur(gray, 5)
        
        # Apply dilation and erosion to remove noise
        kernel = np.ones((1, 1), np.uint8)
        denoised = cv2.dilate(denoised, kernel, iterations=1)
        denoised = cv2.erode(denoised, kernel, iterations=1)
        
        # Apply Gaussian blur
        denoised = cv2.GaussianBlur(denoised, (5, 5), 0)
        
        # Apply threshold to get image with only black and white
        _, processed = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Save processed image
        if output_path is None:
            output_path = tempfile.mktemp(suffix='.png')
        
        cv2.imwrite(output_path, processed)
        
        logger.info(f"Preprocessed image saved to: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Image preprocessing failed: {e}")
        raise


def detect_document_orientation(image_path: str) -> int:
    """Detect document orientation and return rotation angle."""
    
    try:
        # Read image
        image = cv2.imread(image_path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Use HoughLines to detect lines
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=100)
        
        if lines is not None:
            angles = []
            for rho, theta in lines[:10]:  # Use first 10 lines
                angle = np.degrees(theta)
                # Convert to standard rotation angles
                if angle > 45 and angle <= 135:
                    angle = angle - 90
                angles.append(angle)
            
            # Return most common angle
            if angles:
                return int(np.median(angles))
        
        return 0  # No rotation needed
        
    except Exception as e:
        logger.warning(f"Orientation detection failed: {e}")
        return 0


def rotate_image(image_path: str, angle: int, output_path: Optional[str] = None) -> str:
    """Rotate image by specified angle."""
    
    try:
        image = cv2.imread(image_path)
        height, width = image.shape[:2]
        
        # Calculate rotation matrix
        center = (width // 2, height // 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        # Apply rotation
        rotated = cv2.warpAffine(image, rotation_matrix, (width, height), 
                               flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
        
        # Save rotated image
        if output_path is None:
            output_path = tempfile.mktemp(suffix='.png')
        
        cv2.imwrite(output_path, rotated)
        
        logger.info(f"Rotated image saved to: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Image rotation failed: {e}")
        raise


def extract_image_from_pdf(pdf_path: str, page_number: int, output_dir: str) -> str:
    """Extract image from PDF page."""
    
    try:
        doc = fitz.open(pdf_path)
        
        if page_number < 1 or page_number > len(doc):
            doc.close()
            raise ValueError(f"Page {page_number} not found in PDF")
        
        page = doc[page_number - 1]
        
        # High resolution for better OCR
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom = 144 DPI
        pix = page.get_pixmap(matrix=mat)
        
        # Save as PNG
        output_path = os.path.join(output_dir, f"page_{page_number}.png")
        pix.save(output_path)
        
        doc.close()
        
        logger.info(f"Extracted page {page_number} to: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Image extraction failed: {e}")
        raise


def create_thumbnail(image_path: str, max_size: Tuple[int, int] = (200, 200)) -> bytes:
    """Create a thumbnail of the image."""
    
    try:
        with Image.open(image_path) as image:
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Create thumbnail
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save to bytes
            output = BytesIO()
            image.save(output, format='JPEG', quality=85)
            
            return output.getvalue()
            
    except Exception as e:
        logger.error(f"Thumbnail creation failed: {e}")
        raise