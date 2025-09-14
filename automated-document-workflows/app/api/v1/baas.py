"""
BaaS (Backend as a Service) integration API endpoints.
"""

from typing import Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Document, Job
from app.schemas.baas import (
    BaaSWebhookPayload,
    BaaSHealthCheck,
    BaaSStats,
)
from app.utils.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/status")
async def get_baas_status():
    """Get BaaS integration status."""
    
    return {
        "enabled": settings.baas_enabled,
        "api_key_configured": bool(settings.lv_baas_api_key),
        "workflow_configured": bool(settings.lv_baas_workflow_id),
        "base_url": settings.lv_baas_base_url,
    }


@router.get("/health", response_model=BaaSHealthCheck)
async def check_baas_health():
    """Check BaaS service health."""
    
    if not settings.baas_enabled:
        return BaaSHealthCheck(
            service_available=False,
            api_key_valid=False,
            workflow_exists=False,
            response_time_ms=0,
            last_checked=None,
            error_message="BaaS not enabled",
        )
    
    # TODO: Implement actual health check
    # This would ping the BaaS service and verify credentials
    
    return BaaSHealthCheck(
        service_available=True,
        api_key_valid=True,
        workflow_exists=True,
        response_time_ms=100.0,
        last_checked=None,
        error_message=None,
    )


@router.post("/webhook")
async def baas_webhook(
    request: Request,
    payload: BaaSWebhookPayload,
    db: Session = Depends(get_db),
):
    """Handle webhooks from BaaS service."""
    
    logger.info(f"Received BaaS webhook for job {payload.job_id}")
    
    try:
        # Find the document by BaaS job ID
        document = db.query(Document).filter(Document.baas_job_id == payload.job_id).first()
        if not document:
            logger.warning(f"No document found for BaaS job {payload.job_id}")
            raise HTTPException(status_code=404, detail="Document not found for job ID")
        
        # Update document with BaaS results
        document.baas_status = payload.status
        document.baas_result = {
            "extracted_text": payload.extracted_text,
            "entities": payload.entities,
            "tables": payload.tables,
            "fields": payload.fields,
            "document_type": payload.document_type,
            "language": payload.language,
            "confidence_score": payload.confidence_score,
            "processing_time_ms": payload.processing_time_ms,
            "pages_processed": payload.pages_processed,
            "ocr_engine": payload.ocr_engine,
        }
        
        # Update extracted text if available
        if payload.extracted_text:
            document.extracted_text = payload.extracted_text
            document.has_text = True
        
        if payload.language:
            document.language = payload.language
        
        # Handle completion
        if payload.status in ["completed", "success"]:
            document.status = "completed"
            document.processing_completed_at = payload.completed_at
            
            # TODO: Download and save generated files (searchable PDF, DOCX, etc.)
            # if payload.searchable_pdf_url:
            #     download_and_save_file(payload.searchable_pdf_url, document, "searchable_pdf")
            
        elif payload.status in ["failed", "error"]:
            document.status = "failed"
            document.error_message = payload.error_message
            document.processing_completed_at = payload.completed_at
        
        db.commit()
        
        logger.info(f"Updated document {document.id} with BaaS results")
        
        return {"message": "Webhook processed successfully", "document_id": document.id}
        
    except Exception as e:
        logger.error(f"Failed to process BaaS webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


@router.get("/stats", response_model=BaaSStats)
async def get_baas_stats(
    db: Session = Depends(get_db),
):
    """Get BaaS usage statistics."""
    
    try:
        # Count documents processed via BaaS
        total_baas_docs = db.query(Document).filter(Document.baas_job_id.isnot(None)).count()
        successful_docs = db.query(Document).filter(
            Document.baas_job_id.isnot(None),
            Document.baas_status == "completed"
        ).count()
        failed_docs = db.query(Document).filter(
            Document.baas_job_id.isnot(None),
            Document.baas_status == "failed"
        ).count()
        pending_docs = db.query(Document).filter(
            Document.baas_job_id.isnot(None),
            Document.baas_status.in_(["pending", "processing", "running"])
        ).count()
        
        # Calculate success rate
        success_rate = (successful_docs / total_baas_docs * 100) if total_baas_docs > 0 else 0
        
        # TODO: Calculate other stats from BaaS results
        
        return BaaSStats(
            total_jobs_submitted=total_baas_docs,
            successful_jobs=successful_docs,
            failed_jobs=failed_docs,
            pending_jobs=pending_docs,
            average_processing_time_ms=0.0,  # TODO: Calculate from baas_result data
            success_rate=success_rate,
            total_pages_processed=0,  # TODO: Sum from baas_result data
            total_documents_processed=total_baas_docs,
            cost_estimate=None,
        )
        
    except Exception as e:
        logger.error(f"Failed to get BaaS stats: {e}")
        raise HTTPException(status_code=500, detail="Stats generation failed")