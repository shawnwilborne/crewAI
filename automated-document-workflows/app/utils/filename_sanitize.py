"""
Filename sanitization utilities.
"""

import re
import os
import unicodedata
from typing import Optional
from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger(__name__)


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize filename to be safe for filesystem use.
    
    Args:
        filename: Original filename
        max_length: Maximum length of sanitized filename
        
    Returns:
        Sanitized filename safe for filesystem use
    """
    
    if not filename:
        return "unnamed_file"
    
    try:
        # Normalize unicode characters
        filename = unicodedata.normalize('NFKD', filename)
        
        # Remove or replace problematic characters
        # Keep alphanumeric, dots, hyphens, underscores, spaces, and parentheses
        filename = re.sub(r'[^\w\s\-_\.\(\)]', '_', filename)
        
        # Replace multiple spaces with single space
        filename = re.sub(r'\s+', ' ', filename)
        
        # Replace multiple underscores with single underscore
        filename = re.sub(r'_+', '_', filename)
        
        # Remove leading/trailing spaces and dots
        filename = filename.strip(' .')
        
        # Ensure filename is not empty
        if not filename:
            filename = "unnamed_file"
        
        # Ensure we preserve the file extension
        name_part, ext_part = os.path.splitext(filename)
        
        # Truncate name part if too long, leaving room for extension
        if len(filename) > max_length:
            available_length = max_length - len(ext_part)
            if available_length > 0:
                name_part = name_part[:available_length]
                filename = name_part + ext_part
            else:
                # Extension is too long, just truncate everything
                filename = filename[:max_length]
        
        # Ensure filename doesn't start with a dot (hidden file)
        if filename.startswith('.') and len(filename) > 1:
            filename = '_' + filename[1:]
        
        logger.debug(f"Sanitized filename: '{filename}'")
        return filename
        
    except Exception as e:
        logger.error(f"Filename sanitization failed: {e}")
        return "unnamed_file"


def sanitize_path(path: str) -> str:
    """
    Sanitize a file path to be safe for filesystem use.
    
    Args:
        path: Original file path
        
    Returns:
        Sanitized path safe for filesystem use
    """
    
    try:
        # Convert to Path object for easier manipulation
        path_obj = Path(path)
        
        # Sanitize each part of the path
        parts = []
        for part in path_obj.parts:
            if part in ('/', '\\', '.', '..'):
                continue  # Skip problematic path components
            sanitized_part = sanitize_filename(part)
            if sanitized_part and sanitized_part != '.':
                parts.append(sanitized_part)
        
        # Reconstruct path
        if not parts:
            return "unnamed_path"
        
        sanitized_path = os.path.join(*parts)
        
        logger.debug(f"Sanitized path: '{sanitized_path}'")
        return sanitized_path
        
    except Exception as e:
        logger.error(f"Path sanitization failed: {e}")
        return "unnamed_path"


def generate_unique_filename(directory: str, base_filename: str) -> str:
    """
    Generate a unique filename in the given directory.
    
    Args:
        directory: Target directory
        base_filename: Base filename
        
    Returns:
        Unique filename that doesn't exist in the directory
    """
    
    try:
        # Sanitize the base filename
        base_filename = sanitize_filename(base_filename)
        
        # Split name and extension
        name_part, ext_part = os.path.splitext(base_filename)
        
        # Check if base filename is available
        full_path = os.path.join(directory, base_filename)
        if not os.path.exists(full_path):
            return base_filename
        
        # Generate unique filename with counter
        counter = 1
        while counter < 10000:  # Reasonable limit
            new_filename = f"{name_part}_{counter}{ext_part}"
            full_path = os.path.join(directory, new_filename)
            
            if not os.path.exists(full_path):
                logger.debug(f"Generated unique filename: '{new_filename}'")
                return new_filename
            
            counter += 1
        
        # If we can't find a unique name, add timestamp
        import time
        timestamp = int(time.time())
        unique_filename = f"{name_part}_{timestamp}{ext_part}"
        
        logger.warning(f"Using timestamp-based filename: '{unique_filename}'")
        return unique_filename
        
    except Exception as e:
        logger.error(f"Unique filename generation failed: {e}")
        import time
        return f"file_{int(time.time())}.dat"


def is_safe_filename(filename: str) -> bool:
    """
    Check if filename is safe for filesystem use.
    
    Args:
        filename: Filename to check
        
    Returns:
        True if filename is safe, False otherwise
    """
    
    if not filename:
        return False
    
    # Check for problematic patterns
    unsafe_patterns = [
        r'^\.',  # Hidden files
        r'^CON$|^PRN$|^AUX$|^NUL$',  # Windows reserved names
        r'^COM[1-9]$|^LPT[1-9]$',  # Windows reserved names
        r'[<>:"|?*]',  # Invalid characters
        r'[\x00-\x1f]',  # Control characters
    ]
    
    for pattern in unsafe_patterns:
        if re.search(pattern, filename, re.IGNORECASE):
            return False
    
    # Check length
    if len(filename) > 255:
        return False
    
    # Check if filename ends with space or dot
    if filename.endswith(' ') or filename.endswith('.'):
        return False
    
    return True


def extract_file_info(filename: str) -> dict:
    """
    Extract information from filename.
    
    Args:
        filename: Filename to analyze
        
    Returns:
        Dictionary with file information
    """
    
    try:
        # Basic path info
        path_obj = Path(filename)
        
        info = {
            'name': path_obj.stem,
            'extension': path_obj.suffix.lower().lstrip('.'),
            'full_name': path_obj.name,
            'is_hidden': path_obj.name.startswith('.'),
            'has_extension': bool(path_obj.suffix),
        }
        
        # Try to extract date patterns
        date_patterns = [
            r'(\d{4})-(\d{2})-(\d{2})',  # YYYY-MM-DD
            r'(\d{2})-(\d{2})-(\d{4})',  # DD-MM-YYYY or MM-DD-YYYY
            r'(\d{4})(\d{2})(\d{2})',    # YYYYMMDD
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, filename)
            if match:
                info['has_date'] = True
                info['date_match'] = match.group()
                break
        else:
            info['has_date'] = False
            info['date_match'] = None
        
        # Try to extract version patterns
        version_patterns = [
            r'v(\d+)\.(\d+)',  # v1.2
            r'version[_\s]?(\d+)',  # version_1, version 1
            r'\((\d+)\)',  # (1)
        ]
        
        for pattern in version_patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                info['has_version'] = True
                info['version_match'] = match.group()
                break
        else:
            info['has_version'] = False
            info['version_match'] = None
        
        # Document type hints
        doc_type_keywords = {
            'invoice': ['invoice', 'bill', 'receipt'],
            'contract': ['contract', 'agreement', 'terms'],
            'report': ['report', 'analysis', 'summary'],
            'statement': ['statement', 'bank', 'financial'],
            'form': ['form', 'application', 'request'],
        }
        
        detected_types = []
        filename_lower = filename.lower()
        
        for doc_type, keywords in doc_type_keywords.items():
            if any(keyword in filename_lower for keyword in keywords):
                detected_types.append(doc_type)
        
        info['document_types'] = detected_types
        info['primary_type'] = detected_types[0] if detected_types else 'document'
        
        return info
        
    except Exception as e:
        logger.error(f"File info extraction failed: {e}")
        return {
            'name': 'unknown',
            'extension': '',
            'full_name': filename,
            'is_hidden': False,
            'has_extension': False,
            'has_date': False,
            'date_match': None,
            'has_version': False,
            'version_match': None,
            'document_types': [],
            'primary_type': 'document',
        }