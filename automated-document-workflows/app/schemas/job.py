"""
Pydantic schemas for job-related API models.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, validator

from app.db.models import JobStatus, StepStatus, StepType


class JobBase(BaseModel):
    """Base job schema."""
    job_type: str = Field(..., description="Type of processing job")
    priority: int = Field(0, description="Job priority (higher = more priority)")
    config: Optional[Dict[str, Any]] = Field(None, description="Job configuration")


class JobCreate(JobBase):
    """Schema for creating a new job."""
    document_id: UUID = Field(..., description="Document ID to process")


class JobUpdate(BaseModel):
    """Schema for updating job status."""
    status: Optional[JobStatus] = None
    progress: Optional[float] = Field(None, ge=0.0, le=100.0)
    current_step: Optional[str] = None
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class StepBase(BaseModel):
    """Base step schema."""
    step_type: StepType = Field(..., description="Type of processing step")
    step_name: str = Field(..., description="Human-readable step name")
    sequence_order: int = Field(..., description="Order in the pipeline")
    config: Optional[Dict[str, Any]] = Field(None, description="Step configuration")


class StepCreate(StepBase):
    """Schema for creating a new step."""
    job_id: UUID = Field(..., description="Job ID")


class StepUpdate(BaseModel):
    """Schema for updating step status."""
    status: Optional[StepStatus] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    memory_usage_mb: Optional[float] = None


class Step(StepBase):
    """Schema for step response."""
    id: UUID
    job_id: UUID
    status: StepStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Job(JobBase):
    """Schema for job response."""
    id: UUID
    document_id: UUID
    status: JobStatus
    progress: float = 0.0
    current_step: Optional[str] = None
    worker_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    result: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    
    # Related data
    steps: List[Step] = []

    class Config:
        from_attributes = True


class JobSummary(BaseModel):
    """Summary schema for job listings."""
    id: UUID
    document_id: UUID
    job_type: str
    status: JobStatus
    progress: float
    current_step: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobList(BaseModel):
    """Schema for paginated job listings."""
    jobs: List[JobSummary]
    total: int
    page: int = 1
    per_page: int = 50
    pages: int


class JobRunRequest(BaseModel):
    """Schema for running a job."""
    force_restart: bool = Field(False, description="Force restart from beginning")
    skip_completed_steps: bool = Field(True, description="Skip already completed steps")
    config_override: Optional[Dict[str, Any]] = Field(None, description="Override job config")


class JobRunResponse(BaseModel):
    """Response schema for job run requests."""
    id: UUID
    status: JobStatus
    message: str
    started: bool = True


class JobStats(BaseModel):
    """Job processing statistics."""
    total_jobs: int
    by_status: Dict[str, int]
    by_job_type: Dict[str, int]
    average_processing_time: float
    success_rate: float
    current_queue_size: int
    active_workers: int


class JobSearchRequest(BaseModel):
    """Schema for job search requests."""
    document_id: Optional[UUID] = Field(None, description="Filter by document ID")
    job_type: Optional[str] = Field(None, description="Filter by job type")
    status: Optional[JobStatus] = Field(None, description="Filter by status")
    worker_id: Optional[str] = Field(None, description="Filter by worker ID")
    date_from: Optional[datetime] = Field(None, description="Created after date")
    date_to: Optional[datetime] = Field(None, description="Created before date")
    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(50, ge=1, le=100, description="Items per page")
    sort_by: Optional[str] = Field("created_at", description="Sort field")
    sort_order: Optional[str] = Field("desc", description="Sort order (asc/desc)")

    @validator("sort_order")
    def validate_sort_order(cls, v):
        if v not in ["asc", "desc"]:
            raise ValueError("Sort order must be 'asc' or 'desc'")
        return v


class PipelineConfig(BaseModel):
    """Configuration for document processing pipeline."""
    
    # OCR settings
    ocr_enabled: bool = True
    ocr_language: str = "eng"
    ocr_engine: str = "tesseract"  # tesseract, baas
    ocr_dpi: int = 300
    
    # Conversion settings
    convert_to_docx: bool = True
    convert_to_searchable_pdf: bool = True
    preserve_formatting: bool = True
    
    # Template settings
    apply_template: bool = False
    template_name: Optional[str] = None
    template_data: Optional[Dict[str, Any]] = None
    
    # Routing settings
    apply_routing: bool = True
    routing_rules: Optional[List[str]] = None  # Rule names to apply
    
    # Bates numbering
    apply_bates: bool = False
    bates_prefix: Optional[str] = None
    bates_start: Optional[int] = None
    bates_position: str = "bottom_right"  # top_left, top_right, bottom_left, bottom_right
    
    # Delivery settings
    auto_deliver: bool = False
    delivery_targets: Optional[List[str]] = None  # s3, sftp, shopify, local
    
    # Quality settings
    min_confidence_score: float = 0.7
    skip_low_confidence: bool = False
    
    # Performance settings
    max_pages: Optional[int] = None
    timeout_seconds: int = 3600
    
    @validator("bates_position")
    def validate_bates_position(cls, v):
        valid_positions = ["top_left", "top_right", "bottom_left", "bottom_right"]
        if v not in valid_positions:
            raise ValueError(f"Bates position must be one of: {valid_positions}")
        return v