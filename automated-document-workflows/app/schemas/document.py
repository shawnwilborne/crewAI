"""
Pydantic schemas for document-related API models.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, validator

from app.db.models import DocumentStatus


class DocumentBase(BaseModel):
    """Base document schema."""
    filename: str = Field(..., description="Original filename")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    mime_type: Optional[str] = Field(None, description="MIME type")


class DocumentCreate(DocumentBase):
    """Schema for creating a new document."""
    pass


class DocumentUpdate(BaseModel):
    """Schema for updating document metadata."""
    filename: Optional[str] = None
    status: Optional[DocumentStatus] = None
    error_message: Optional[str] = None
    extracted_text: Optional[str] = None
    language: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PageBase(BaseModel):
    """Base page schema."""
    page_number: int = Field(..., description="Page number (1-indexed)")
    extracted_text: Optional[str] = Field(None, description="Extracted text content")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="OCR confidence score")


class PageCreate(PageBase):
    """Schema for creating a new page."""
    pass


class Page(PageBase):
    """Schema for page response."""
    id: UUID
    document_id: UUID
    ocr_engine: Optional[str] = None
    ocr_language: Optional[str] = None
    ocr_processed_at: Optional[datetime] = None
    thumbnail_path: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    bates_number: Optional[str] = None
    bates_prefix: Optional[str] = None
    bates_sequence: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Document(DocumentBase):
    """Schema for document response."""
    id: UUID
    original_filename: str
    file_path: str
    content_type: Optional[str] = None
    md5_hash: str
    sha256_hash: Optional[str] = None
    page_count: int = 0
    has_text: bool = False
    language: str = "en"
    extracted_text: Optional[str] = None
    status: DocumentStatus
    error_message: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    baas_job_id: Optional[str] = None
    baas_status: Optional[str] = None
    baas_result: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    
    # Related data
    pages: List[Page] = []

    class Config:
        from_attributes = True


class DocumentSummary(BaseModel):
    """Summary schema for document listings."""
    id: UUID
    filename: str
    file_size: int
    mime_type: str
    page_count: int
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentList(BaseModel):
    """Schema for paginated document listings."""
    documents: List[DocumentSummary]
    total: int
    page: int = 1
    per_page: int = 50
    pages: int


class DocumentUploadResponse(BaseModel):
    """Response schema for document upload."""
    id: UUID
    filename: str
    file_size: int
    mime_type: str
    status: DocumentStatus
    job_id: Optional[UUID] = None
    message: str = "Document uploaded successfully"


class PageImageRequest(BaseModel):
    """Request schema for page image generation."""
    width: Optional[int] = Field(None, ge=100, le=2000, description="Image width in pixels")
    height: Optional[int] = Field(None, ge=100, le=2000, description="Image height in pixels")
    dpi: Optional[int] = Field(150, ge=72, le=600, description="DPI for image generation")
    format: Optional[str] = Field("PNG", description="Image format (PNG, JPEG)")

    @validator("format")
    def validate_format(cls, v):
        if v.upper() not in ["PNG", "JPEG", "JPG"]:
            raise ValueError("Format must be PNG or JPEG")
        return v.upper()


class DocumentStats(BaseModel):
    """Document processing statistics."""
    total_documents: int
    by_status: Dict[str, int]
    by_mime_type: Dict[str, int]
    average_file_size: float
    total_file_size: int
    average_pages: float
    total_pages: int
    processing_time_stats: Dict[str, float]  # min, max, avg


class DocumentSearchRequest(BaseModel):
    """Schema for document search requests."""
    query: Optional[str] = Field(None, description="Text search query")
    filename: Optional[str] = Field(None, description="Filename pattern")
    mime_type: Optional[str] = Field(None, description="MIME type filter")
    status: Optional[DocumentStatus] = Field(None, description="Status filter")
    date_from: Optional[datetime] = Field(None, description="Created after date")
    date_to: Optional[datetime] = Field(None, description="Created before date")
    has_text: Optional[bool] = Field(None, description="Filter by text availability")
    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(50, ge=1, le=100, description="Items per page")
    sort_by: Optional[str] = Field("created_at", description="Sort field")
    sort_order: Optional[str] = Field("desc", description="Sort order (asc/desc)")

    @validator("sort_order")
    def validate_sort_order(cls, v):
        if v not in ["asc", "desc"]:
            raise ValueError("Sort order must be 'asc' or 'desc'")
        return v