"""
Pydantic schemas for output-related API models.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.db.models import DeliveryStatus


class OutputBase(BaseModel):
    """Base output schema."""
    filename: str = Field(..., description="Output filename")
    output_type: str = Field(..., description="Type of output (pdf, docx, html, etc.)")
    description: Optional[str] = Field(None, description="Output description")


class OutputCreate(OutputBase):
    """Schema for creating a new output."""
    document_id: UUID = Field(..., description="Source document ID")
    file_path: str = Field(..., description="File path on disk")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    format_type: str = Field(..., description="File format")


class OutputUpdate(BaseModel):
    """Schema for updating output metadata."""
    delivery_status: Optional[DeliveryStatus] = None
    delivery_target: Optional[str] = None
    delivery_path: Optional[str] = None
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    quality_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    metadata: Optional[Dict[str, Any]] = None


class Output(OutputBase):
    """Schema for output response."""
    id: UUID
    document_id: UUID
    file_path: str
    file_size: int
    mime_type: str
    format_type: str
    delivery_status: DeliveryStatus
    delivery_target: Optional[str] = None
    delivery_path: Optional[str] = None
    delivered_at: Optional[datetime] = None
    confidence_score: Optional[float] = None
    quality_score: Optional[float] = None
    bates_start: Optional[int] = None
    bates_end: Optional[int] = None
    bates_prefix: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OutputSummary(BaseModel):
    """Summary schema for output listings."""
    id: UUID
    document_id: UUID
    filename: str
    file_size: int
    output_type: str
    format_type: str
    delivery_status: DeliveryStatus
    created_at: datetime

    class Config:
        from_attributes = True


class OutputList(BaseModel):
    """Schema for paginated output listings."""
    outputs: List[OutputSummary]
    total: int
    page: int = 1
    per_page: int = 50
    pages: int


class OutputDownloadResponse(BaseModel):
    """Response schema for output download."""
    filename: str
    file_size: int
    mime_type: str
    download_url: str
    expires_at: Optional[datetime] = None


class OutputBatch(BaseModel):
    """Schema for batch output operations."""
    output_ids: List[UUID] = Field(..., description="List of output IDs")
    operation: str = Field(..., description="Batch operation (download, deliver, delete)")
    target: Optional[str] = Field(None, description="Target for delivery operations")
    config: Optional[Dict[str, Any]] = Field(None, description="Operation configuration")


class OutputBatchResponse(BaseModel):
    """Response schema for batch operations."""
    operation: str
    total: int
    successful: int
    failed: int
    results: List[Dict[str, Any]]
    batch_id: Optional[UUID] = None


class OutputStats(BaseModel):
    """Output generation statistics."""
    total_outputs: int
    by_type: Dict[str, int]
    by_format: Dict[str, int]
    by_delivery_status: Dict[str, int]
    total_size_bytes: int
    average_size_bytes: float
    average_confidence_score: Optional[float] = None
    average_quality_score: Optional[float] = None


class OutputSearchRequest(BaseModel):
    """Schema for output search requests."""
    document_id: Optional[UUID] = Field(None, description="Filter by document ID")
    output_type: Optional[str] = Field(None, description="Filter by output type")
    format_type: Optional[str] = Field(None, description="Filter by format type")
    delivery_status: Optional[DeliveryStatus] = Field(None, description="Filter by delivery status")
    delivery_target: Optional[str] = Field(None, description="Filter by delivery target")
    date_from: Optional[datetime] = Field(None, description="Created after date")
    date_to: Optional[datetime] = Field(None, description="Created before date")
    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum confidence score")
    min_quality: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum quality score")
    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(50, ge=1, le=100, description="Items per page")
    sort_by: Optional[str] = Field("created_at", description="Sort field")
    sort_order: Optional[str] = Field("desc", description="Sort order (asc/desc)")


class DeliveryRequest(BaseModel):
    """Schema for output delivery requests."""
    target: str = Field(..., description="Delivery target (s3, sftp, shopify, local)")
    destination: Optional[str] = Field(None, description="Destination path/bucket/folder")
    config: Optional[Dict[str, Any]] = Field(None, description="Target-specific configuration")
    overwrite: bool = Field(False, description="Overwrite existing files")
    verify: bool = Field(True, description="Verify delivery success")


class DeliveryResponse(BaseModel):
    """Response schema for delivery operations."""
    output_id: UUID
    target: str
    destination: str
    status: DeliveryStatus
    delivered_at: Optional[datetime] = None
    delivery_path: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ExportRequest(BaseModel):
    """Schema for exporting multiple outputs."""
    output_ids: List[UUID] = Field(..., description="List of output IDs to export")
    format: str = Field("zip", description="Export format (zip, tar)")
    include_metadata: bool = Field(True, description="Include metadata JSON")
    filename: Optional[str] = Field(None, description="Custom export filename")


class ExportResponse(BaseModel):
    """Response schema for export operations."""
    export_id: UUID
    filename: str
    file_size: int
    download_url: str
    expires_at: datetime
    included_outputs: int
    created_at: datetime