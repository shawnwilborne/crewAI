"""
Document management API endpoints.
"""

import os
import hashlib
import mimetypes
from typing import List, Optional
from uuid import UUID
from io import BytesIO

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, and_, or_

from app.db.database import get_db
from app.db.models import Document, Page, Job, DocumentStatus, JobStatus
from app.schemas.document import (
    Document as DocumentSchema,
    DocumentSummary,
    DocumentList,
    DocumentUploadResponse,
    DocumentUpdate,
    DocumentSearchRequest,
    DocumentStats,
    PageImageRequest,
    Page as PageSchema,
)
from app.schemas.job import JobCreate, PipelineConfig
from app.services.pipeline import DocumentProcessor
from app.utils.settings import settings
from app.utils.logging import get_logger, log_document_event
from app.utils.image_preprocess import generate_page_image
from app.utils.filename_sanitize import sanitize_filename
from app.worker import process_document_task

logger = get_logger(__name__)
router = APIRouter()


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    auto_process: bool = Query(True, description="Automatically start processing"),
    pipeline_config: Optional[str] = Query(None, description="JSON pipeline configuration"),
    db: Session = Depends(get_db),
):
    """Upload a new document for processing."""
    
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    # Check file size
    content = await file.read()
    file_size = len(content)
    max_size = settings.get_max_file_size_bytes()
    
    if file_size > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File size {file_size} exceeds maximum {max_size} bytes"
        )
    
    # Validate file type
    mime_type = file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
    file_extension = os.path.splitext(file.filename)[1][1:].lower()
    
    if file_extension not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file_extension}' not allowed. Allowed types: {settings.allowed_extensions}"
        )
    
    # Generate file hashes
    md5_hash = hashlib.md5(content).hexdigest()
    sha256_hash = hashlib.sha256(content).hexdigest()
    
    # Check for duplicate
    existing_doc = db.query(Document).filter(Document.md5_hash == md5_hash).first()
    if existing_doc:
        log_document_event(
            str(existing_doc.id),
            "upload",
            "duplicate_detected",
            success=True,
            metadata={"original_filename": file.filename}
        )
        return DocumentUploadResponse(
            id=existing_doc.id,
            filename=existing_doc.filename,
            file_size=existing_doc.file_size,
            mime_type=existing_doc.mime_type,
            status=existing_doc.status,
            message="Document already exists (duplicate detected)"
        )
    
    try:
        # Create upload directory if it doesn't exist
        os.makedirs(settings.temp_upload_dir, exist_ok=True)
        
        # Generate unique filename
        sanitized_filename = sanitize_filename(file.filename)
        unique_filename = f"{md5_hash[:8]}_{sanitized_filename}"
        file_path = os.path.join(settings.temp_upload_dir, unique_filename)
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Create document record
        document = Document(
            filename=sanitized_filename,
            original_filename=file.filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            md5_hash=md5_hash,
            sha256_hash=sha256_hash,
            status=DocumentStatus.UPLOADED,
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        log_document_event(
            str(document.id),
            "upload",
            "document_uploaded",
            success=True,
            metadata={
                "filename": file.filename,
                "file_size": file_size,
                "mime_type": mime_type,
            }
        )
        
        job_id = None
        
        # Auto-start processing if requested
        if auto_process:
            try:
                # Parse pipeline config if provided
                config = {}
                if pipeline_config:
                    import json
                    config = json.loads(pipeline_config)
                
                # Create processing job
                job = Job(
                    document_id=document.id,
                    job_type="full_pipeline",
                    config=config,
                    status=JobStatus.PENDING,
                )
                
                db.add(job)
                db.commit()
                db.refresh(job)
                job_id = job.id
                
                # Start background processing
                background_tasks.add_task(process_document_task.delay, str(job.id))
                
                log_document_event(
                    str(document.id),
                    "processing",
                    "job_created",
                    success=True,
                    metadata={"job_id": str(job.id)}
                )
                
            except Exception as e:
                logger.error(f"Failed to create processing job: {e}")
                # Don't fail the upload, just log the error
        
        return DocumentUploadResponse(
            id=document.id,
            filename=document.filename,
            file_size=document.file_size,
            mime_type=document.mime_type,
            status=document.status,
            job_id=job_id,
            message="Document uploaded successfully"
        )
        
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        
        # Clean up file if it was saved
        if 'file_path' in locals() and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/", response_model=DocumentList)
async def list_documents(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    status: Optional[DocumentStatus] = Query(None, description="Filter by status"),
    mime_type: Optional[str] = Query(None, description="Filter by MIME type"),
    search: Optional[str] = Query(None, description="Search in filename or text"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    db: Session = Depends(get_db),
):
    """List documents with filtering and pagination."""
    
    query = db.query(Document)
    
    # Apply filters
    if status:
        query = query.filter(Document.status == status)
    
    if mime_type:
        query = query.filter(Document.mime_type.contains(mime_type))
    
    if search:
        search_filter = or_(
            Document.filename.contains(search),
            Document.original_filename.contains(search),
            Document.extracted_text.contains(search)
        )
        query = query.filter(search_filter)
    
    # Get total count
    total = query.count()
    
    # Apply sorting
    sort_column = getattr(Document, sort_by, Document.created_at)
    if sort_order.lower() == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
    
    # Apply pagination
    offset = (page - 1) * per_page
    documents = query.offset(offset).limit(per_page).all()
    
    # Calculate pages
    pages = (total + per_page - 1) // per_page
    
    return DocumentList(
        documents=[DocumentSummary.from_orm(doc) for doc in documents],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get("/{document_id}", response_model=DocumentSchema)
async def get_document(
    document_id: UUID,
    include_pages: bool = Query(False, description="Include page information"),
    db: Session = Depends(get_db),
):
    """Get document details by ID."""
    
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Load pages if requested
    if include_pages:
        pages = db.query(Page).filter(Page.document_id == document_id).order_by(Page.page_number).all()
        document.pages = [PageSchema.from_orm(page) for page in pages]
    
    return DocumentSchema.from_orm(document)


@router.patch("/{document_id}", response_model=DocumentSchema)
async def update_document(
    document_id: UUID,
    update_data: DocumentUpdate,
    db: Session = Depends(get_db),
):
    """Update document metadata."""
    
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(document, field, value)
    
    db.commit()
    db.refresh(document)
    
    log_document_event(
        str(document_id),
        "update",
        "metadata_updated",
        success=True,
        metadata=update_dict
    )
    
    return DocumentSchema.from_orm(document)


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    force: bool = Query(False, description="Force delete even if processing"),
    db: Session = Depends(get_db),
):
    """Delete a document and its associated data."""
    
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check if document is being processed
    if not force and document.status == DocumentStatus.PROCESSING:
        raise HTTPException(
            status_code=400,
            detail="Document is being processed. Use force=true to delete anyway."
        )
    
    try:
        # Delete physical file
        if os.path.exists(document.file_path):
            os.remove(document.file_path)
        
        # Delete from database (cascade will handle related records)
        db.delete(document)
        db.commit()
        
        log_document_event(
            str(document_id),
            "delete",
            "document_deleted",
            success=True,
            metadata={"force": force}
        )
        
        return {"message": "Document deleted successfully"}
        
    except Exception as e:
        logger.error(f"Failed to delete document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    db: Session = Depends(get_db),
):
    """Download the original document file."""
    
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if not os.path.exists(document.file_path):
        raise HTTPException(status_code=404, detail="Document file not found on disk")
    
    return FileResponse(
        path=document.file_path,
        filename=document.original_filename,
        media_type=document.mime_type,
    )


@router.get("/{document_id}/pages/{page_number}/image")
async def get_page_image(
    document_id: UUID,
    page_number: int,
    request: PageImageRequest = Depends(),
    db: Session = Depends(get_db),
):
    """Get a rendered image of a specific page."""
    
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    page = db.query(Page).filter(
        and_(Page.document_id == document_id, Page.page_number == page_number)
    ).first()
    
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    try:
        # Generate page image
        image_bytes = generate_page_image(
            document.file_path,
            page_number,
            width=request.width,
            height=request.height,
            dpi=request.dpi,
            format=request.format,
        )
        
        media_type = "image/png" if request.format == "PNG" else "image/jpeg"
        
        return StreamingResponse(
            BytesIO(image_bytes),
            media_type=media_type,
            headers={"Content-Disposition": f"inline; filename=page_{page_number}.{request.format.lower()}"}
        )
        
    except Exception as e:
        logger.error(f"Failed to generate page image: {e}")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")


@router.post("/{document_id}/process", response_model=dict)
async def process_document(
    document_id: UUID,
    config: Optional[PipelineConfig] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """Start processing a document."""
    
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if document.status == DocumentStatus.PROCESSING:
        raise HTTPException(status_code=400, detail="Document is already being processed")
    
    try:
        # Create processing job
        job_config = config.dict() if config else {}
        
        job = Job(
            document_id=document_id,
            job_type="full_pipeline",
            config=job_config,
            status=JobStatus.PENDING,
        )
        
        db.add(job)
        db.commit()
        db.refresh(job)
        
        # Update document status
        document.status = DocumentStatus.PROCESSING
        db.commit()
        
        # Start background processing
        background_tasks.add_task(process_document_task.delay, str(job.id))
        
        log_document_event(
            str(document_id),
            "processing",
            "processing_started",
            success=True,
            metadata={"job_id": str(job.id)}
        )
        
        return {
            "message": "Document processing started",
            "job_id": job.id,
            "document_id": document_id,
        }
        
    except Exception as e:
        logger.error(f"Failed to start processing: {e}")
        raise HTTPException(status_code=500, detail=f"Processing start failed: {str(e)}")


@router.get("/stats", response_model=DocumentStats)
async def get_document_stats(
    db: Session = Depends(get_db),
):
    """Get document processing statistics."""
    
    try:
        # Get basic counts
        total_documents = db.query(Document).count()
        
        # Count by status
        status_counts = {}
        for status in DocumentStatus:
            count = db.query(Document).filter(Document.status == status).count()
            status_counts[status.value] = count
        
        # Count by MIME type
        mime_type_query = db.query(Document.mime_type, db.func.count(Document.id)).group_by(Document.mime_type).all()
        mime_type_counts = {mime_type: count for mime_type, count in mime_type_query}
        
        # Calculate averages
        size_stats = db.query(
            db.func.avg(Document.file_size),
            db.func.sum(Document.file_size),
        ).first()
        
        page_stats = db.query(
            db.func.avg(Document.page_count),
            db.func.sum(Document.page_count),
        ).first()
        
        average_file_size = float(size_stats[0]) if size_stats[0] else 0
        total_file_size = int(size_stats[1]) if size_stats[1] else 0
        average_pages = float(page_stats[0]) if page_stats[0] else 0
        total_pages = int(page_stats[1]) if page_stats[1] else 0
        
        # Processing time stats (from completed jobs)
        processing_time_stats = {"min": 0, "max": 0, "avg": 0}
        
        return DocumentStats(
            total_documents=total_documents,
            by_status=status_counts,
            by_mime_type=mime_type_counts,
            average_file_size=average_file_size,
            total_file_size=total_file_size,
            average_pages=average_pages,
            total_pages=total_pages,
            processing_time_stats=processing_time_stats,
        )
        
    except Exception as e:
        logger.error(f"Failed to get document stats: {e}")
        raise HTTPException(status_code=500, detail=f"Stats generation failed: {str(e)}")


@router.post("/search", response_model=DocumentList)
async def search_documents(
    search_request: DocumentSearchRequest,
    db: Session = Depends(get_db),
):
    """Advanced document search with multiple filters."""
    
    query = db.query(Document)
    
    # Apply text search
    if search_request.query:
        search_filter = or_(
            Document.filename.contains(search_request.query),
            Document.original_filename.contains(search_request.query),
            Document.extracted_text.contains(search_request.query)
        )
        query = query.filter(search_filter)
    
    # Apply filters
    if search_request.filename:
        query = query.filter(Document.filename.contains(search_request.filename))
    
    if search_request.mime_type:
        query = query.filter(Document.mime_type == search_request.mime_type)
    
    if search_request.status:
        query = query.filter(Document.status == search_request.status)
    
    if search_request.date_from:
        query = query.filter(Document.created_at >= search_request.date_from)
    
    if search_request.date_to:
        query = query.filter(Document.created_at <= search_request.date_to)
    
    if search_request.has_text is not None:
        query = query.filter(Document.has_text == search_request.has_text)
    
    # Get total count
    total = query.count()
    
    # Apply sorting
    sort_column = getattr(Document, search_request.sort_by, Document.created_at)
    if search_request.sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
    
    # Apply pagination
    offset = (search_request.page - 1) * search_request.per_page
    documents = query.offset(offset).limit(search_request.per_page).all()
    
    # Calculate pages
    pages = (total + search_request.per_page - 1) // search_request.per_page
    
    return DocumentList(
        documents=[DocumentSummary.from_orm(doc) for doc in documents],
        total=total,
        page=search_request.page,
        per_page=search_request.per_page,
        pages=pages,
    )