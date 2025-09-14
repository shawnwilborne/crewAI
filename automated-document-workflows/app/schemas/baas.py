"""
Pydantic schemas for BaaS (Backend as a Service) integration.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class BaaSJobRequest(BaseModel):
    """Schema for BaaS job submission."""
    workflow_id: str = Field(..., description="BaaS workflow identifier")
    document_id: UUID = Field(..., description="Internal document ID")
    file_path: str = Field(..., description="Path to file for processing")
    callback_url: Optional[str] = Field(None, description="Webhook callback URL")
    priority: int = Field(0, description="Job priority")
    config: Optional[Dict[str, Any]] = Field(None, description="Processing configuration")


class BaaSJobResponse(BaseModel):
    """Response from BaaS job submission."""
    job_id: str = Field(..., description="BaaS job identifier")
    status: str = Field(..., description="Initial job status")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")
    webhook_url: Optional[str] = Field(None, description="Webhook endpoint for updates")
    created_at: datetime = Field(..., description="Job creation timestamp")


class BaaSJobStatus(BaseModel):
    """BaaS job status response."""
    job_id: str = Field(..., description="BaaS job identifier")
    status: str = Field(..., description="Current job status")
    progress: Optional[float] = Field(None, ge=0.0, le=100.0, description="Completion percentage")
    current_step: Optional[str] = Field(None, description="Current processing step")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    result: Optional[Dict[str, Any]] = Field(None, description="Processing results")
    created_at: datetime = Field(..., description="Job creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")


class BaaSWebhookPayload(BaseModel):
    """Webhook payload from BaaS service."""
    job_id: str = Field(..., description="BaaS job identifier")
    status: str = Field(..., description="Job status")
    progress: Optional[float] = Field(None, description="Completion percentage")
    current_step: Optional[str] = Field(None, description="Current processing step")
    
    # Processing results
    extracted_text: Optional[str] = Field(None, description="Extracted text content")
    entities: Optional[List[Dict[str, Any]]] = Field(None, description="Extracted entities")
    tables: Optional[List[Dict[str, Any]]] = Field(None, description="Extracted tables")
    fields: Optional[Dict[str, Any]] = Field(None, description="Extracted form fields")
    
    # Document analysis
    document_type: Optional[str] = Field(None, description="Detected document type")
    language: Optional[str] = Field(None, description="Detected language")
    confidence_score: Optional[float] = Field(None, description="Overall confidence score")
    
    # Generated outputs
    searchable_pdf_url: Optional[str] = Field(None, description="URL to searchable PDF")
    docx_url: Optional[str] = Field(None, description="URL to DOCX conversion")
    structured_data_url: Optional[str] = Field(None, description="URL to structured data JSON")
    
    # Processing metadata
    processing_time_ms: Optional[int] = Field(None, description="Processing time in milliseconds")
    pages_processed: Optional[int] = Field(None, description="Number of pages processed")
    ocr_engine: Optional[str] = Field(None, description="OCR engine used")
    
    # Error information
    error_code: Optional[str] = Field(None, description="Error code if failed")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_details: Optional[Dict[str, Any]] = Field(None, description="Detailed error information")
    
    # Timestamps
    created_at: datetime = Field(..., description="Job creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")


class BaaSConfig(BaseModel):
    """BaaS service configuration."""
    enabled: bool = Field(False, description="Whether BaaS is enabled")
    api_key: Optional[str] = Field(None, description="BaaS API key")
    workflow_id: Optional[str] = Field(None, description="Default workflow ID")
    base_url: str = Field("https://api.lidvizion.com/v1", description="BaaS API base URL")
    timeout_seconds: int = Field(30, description="Request timeout")
    max_retries: int = Field(3, description="Maximum retry attempts")
    webhook_secret: Optional[str] = Field(None, description="Webhook verification secret")


class BaaSHealthCheck(BaseModel):
    """BaaS service health check response."""
    service_available: bool = Field(..., description="Whether BaaS service is available")
    api_key_valid: bool = Field(..., description="Whether API key is valid")
    workflow_exists: bool = Field(..., description="Whether workflow ID exists")
    response_time_ms: float = Field(..., description="Response time in milliseconds")
    last_checked: datetime = Field(..., description="Last health check timestamp")
    error_message: Optional[str] = Field(None, description="Error message if unhealthy")


class BaaSStats(BaseModel):
    """BaaS usage statistics."""
    total_jobs_submitted: int = Field(..., description="Total jobs submitted to BaaS")
    successful_jobs: int = Field(..., description="Successfully completed jobs")
    failed_jobs: int = Field(..., description="Failed jobs")
    pending_jobs: int = Field(..., description="Currently pending jobs")
    average_processing_time_ms: float = Field(..., description="Average processing time")
    success_rate: float = Field(..., description="Success rate percentage")
    total_pages_processed: int = Field(..., description="Total pages processed")
    total_documents_processed: int = Field(..., description="Total documents processed")
    cost_estimate: Optional[float] = Field(None, description="Estimated cost if available")


class BaaSDocument(BaseModel):
    """Document processed by BaaS."""
    internal_document_id: UUID = Field(..., description="Internal document ID")
    baas_job_id: str = Field(..., description="BaaS job identifier")
    status: str = Field(..., description="Processing status")
    
    # Extracted content
    extracted_text: Optional[str] = Field(None, description="Full extracted text")
    entities: Optional[List[Dict[str, Any]]] = Field(None, description="Named entities")
    tables: Optional[List[Dict[str, Any]]] = Field(None, description="Extracted tables")
    fields: Optional[Dict[str, Any]] = Field(None, description="Form fields")
    
    # Analysis results
    document_type: Optional[str] = Field(None, description="Document classification")
    language: Optional[str] = Field(None, description="Detected language")
    confidence_score: Optional[float] = Field(None, description="Overall confidence")
    
    # Generated files
    has_searchable_pdf: bool = Field(False, description="Whether searchable PDF was generated")
    has_docx: bool = Field(False, description="Whether DOCX was generated")
    has_structured_data: bool = Field(False, description="Whether structured data available")
    
    # Processing info
    processing_time_ms: Optional[int] = Field(None, description="Processing duration")
    pages_processed: int = Field(0, description="Number of pages")
    
    # Timestamps
    submitted_at: datetime = Field(..., description="Submission timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")


class BaaSFallbackConfig(BaseModel):
    """Configuration for BaaS fallback to local processing."""
    enabled: bool = Field(True, description="Enable fallback to local processing")
    fallback_triggers: List[str] = Field(
        default=["service_unavailable", "timeout", "authentication_error"],
        description="Conditions that trigger fallback"
    )
    max_fallback_attempts: int = Field(3, description="Maximum fallback attempts")
    fallback_delay_seconds: int = Field(60, description="Delay before fallback attempt")
    preserve_baas_results: bool = Field(True, description="Keep BaaS results even after fallback")


class BaaSWorkflowInfo(BaseModel):
    """Information about a BaaS workflow."""
    workflow_id: str = Field(..., description="Workflow identifier")
    name: str = Field(..., description="Workflow name")
    description: Optional[str] = Field(None, description="Workflow description")
    supported_formats: List[str] = Field(..., description="Supported file formats")
    processing_steps: List[str] = Field(..., description="Processing steps")
    average_processing_time_ms: Optional[float] = Field(None, description="Average processing time")
    cost_per_page: Optional[float] = Field(None, description="Cost per page if available")
    created_at: datetime = Field(..., description="Workflow creation date")
    updated_at: datetime = Field(..., description="Last update date")


class BaaSBatchRequest(BaseModel):
    """Schema for batch BaaS processing."""
    document_ids: List[UUID] = Field(..., description="List of document IDs to process")
    workflow_id: Optional[str] = Field(None, description="Override workflow ID")
    priority: int = Field(0, description="Batch priority")
    config: Optional[Dict[str, Any]] = Field(None, description="Batch processing config")
    callback_url: Optional[str] = Field(None, description="Batch completion webhook")


class BaaSBatchResponse(BaseModel):
    """Response for batch BaaS processing."""
    batch_id: UUID = Field(..., description="Internal batch identifier")
    submitted_jobs: List[str] = Field(..., description="List of BaaS job IDs")
    total_documents: int = Field(..., description="Total documents in batch")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated batch completion")
    callback_url: Optional[str] = Field(None, description="Batch webhook URL")
    created_at: datetime = Field(..., description="Batch creation timestamp")