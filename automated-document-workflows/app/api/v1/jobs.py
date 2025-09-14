"""
Job management API endpoints.
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, and_, or_

from app.db.database import get_db
from app.db.models import Job, Document, Step, JobStatus, StepStatus
from app.schemas.job import (
    Job as JobSchema,
    JobSummary,
    JobList,
    JobCreate,
    JobUpdate,
    JobRunRequest,
    JobRunResponse,
    JobStats,
    JobSearchRequest,
    Step as StepSchema,
)
from app.utils.logging import get_logger, log_job_event
from app.worker import process_document_task

logger = get_logger(__name__)
router = APIRouter()


@router.post("/", response_model=JobSchema)
async def create_job(
    job_data: JobCreate,
    db: Session = Depends(get_db),
):
    """Create a new processing job."""
    
    # Verify document exists
    document = db.query(Document).filter(Document.id == job_data.document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    try:
        # Create job
        job = Job(
            document_id=job_data.document_id,
            job_type=job_data.job_type,
            priority=job_data.priority,
            config=job_data.config,
            status=JobStatus.PENDING,
        )
        
        db.add(job)
        db.commit()
        db.refresh(job)
        
        log_job_event(
            str(job.id),
            str(job_data.document_id),
            "create",
            "job_created",
            success=True,
            metadata={"job_type": job_data.job_type}
        )
        
        return JobSchema.from_orm(job)
        
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        raise HTTPException(status_code=500, detail=f"Job creation failed: {str(e)}")


@router.get("/", response_model=JobList)
async def list_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    status: Optional[JobStatus] = Query(None, description="Filter by status"),
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    document_id: Optional[UUID] = Query(None, description="Filter by document ID"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    db: Session = Depends(get_db),
):
    """List jobs with filtering and pagination."""
    
    query = db.query(Job)
    
    # Apply filters
    if status:
        query = query.filter(Job.status == status)
    
    if job_type:
        query = query.filter(Job.job_type == job_type)
    
    if document_id:
        query = query.filter(Job.document_id == document_id)
    
    # Get total count
    total = query.count()
    
    # Apply sorting
    sort_column = getattr(Job, sort_by, Job.created_at)
    if sort_order.lower() == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
    
    # Apply pagination
    offset = (page - 1) * per_page
    jobs = query.offset(offset).limit(per_page).all()
    
    # Calculate pages
    pages = (total + per_page - 1) // per_page
    
    return JobList(
        jobs=[JobSummary.from_orm(job) for job in jobs],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get("/{job_id}", response_model=JobSchema)
async def get_job(
    job_id: UUID,
    include_steps: bool = Query(True, description="Include step information"),
    db: Session = Depends(get_db),
):
    """Get job details by ID."""
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Load steps if requested
    if include_steps:
        steps = db.query(Step).filter(Step.job_id == job_id).order_by(Step.sequence_order).all()
        job.steps = [StepSchema.from_orm(step) for step in steps]
    
    return JobSchema.from_orm(job)


@router.patch("/{job_id}", response_model=JobSchema)
async def update_job(
    job_id: UUID,
    update_data: JobUpdate,
    db: Session = Depends(get_db),
):
    """Update job status and metadata."""
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(job, field, value)
    
    # Update timestamps based on status
    if update_data.status:
        if update_data.status == JobStatus.RUNNING and not job.started_at:
            job.started_at = datetime.utcnow()
        elif update_data.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            if not job.completed_at:
                job.completed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(job)
    
    log_job_event(
        str(job_id),
        str(job.document_id),
        "update",
        "job_updated",
        success=True,
        metadata=update_dict
    )
    
    return JobSchema.from_orm(job)


@router.delete("/{job_id}")
async def delete_job(
    job_id: UUID,
    force: bool = Query(False, description="Force delete even if running"),
    db: Session = Depends(get_db),
):
    """Delete a job and its steps."""
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if job is running
    if not force and job.status == JobStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail="Job is currently running. Use force=true to delete anyway."
        )
    
    try:
        db.delete(job)
        db.commit()
        
        log_job_event(
            str(job_id),
            str(job.document_id),
            "delete",
            "job_deleted",
            success=True,
            metadata={"force": force}
        )
        
        return {"message": "Job deleted successfully"}
        
    except Exception as e:
        logger.error(f"Failed to delete job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.post("/{job_id}/run", response_model=JobRunResponse)
async def run_job(
    job_id: UUID,
    request: JobRunRequest = JobRunRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """Start or resume job execution."""
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if job can be started
    if job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Job is already running")
    
    if job.status == JobStatus.COMPLETED and not request.force_restart:
        raise HTTPException(status_code=400, detail="Job already completed. Use force_restart=true to restart.")
    
    try:
        # Update job config if provided
        if request.config_override:
            job.config = {**(job.config or {}), **request.config_override}
        
        # Reset job if force restart
        if request.force_restart:
            job.status = JobStatus.PENDING
            job.progress = 0.0
            job.current_step = None
            job.started_at = None
            job.completed_at = None
            job.error_message = None
            job.result = None
            job.retry_count = 0
            
            # Reset all steps
            steps = db.query(Step).filter(Step.job_id == job_id).all()
            for step in steps:
                step.status = StepStatus.PENDING
                step.started_at = None
                step.completed_at = None
                step.result = None
                step.error_message = None
        
        db.commit()
        
        # Start background processing
        background_tasks.add_task(process_document_task.delay, str(job_id))
        
        log_job_event(
            str(job_id),
            str(job.document_id),
            "run",
            "job_started",
            success=True,
            metadata={
                "force_restart": request.force_restart,
                "config_override": bool(request.config_override)
            }
        )
        
        return JobRunResponse(
            id=job.id,
            status=JobStatus.PENDING,
            message="Job started successfully",
            started=True,
        )
        
    except Exception as e:
        logger.error(f"Failed to start job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Job start failed: {str(e)}")


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: UUID,
    db: Session = Depends(get_db),
):
    """Cancel a running job."""
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status not in [JobStatus.PENDING, JobStatus.RUNNING]:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled")
    
    try:
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.utcnow()
        
        # Cancel running steps
        running_steps = db.query(Step).filter(
            and_(Step.job_id == job_id, Step.status == StepStatus.RUNNING)
        ).all()
        
        for step in running_steps:
            step.status = StepStatus.SKIPPED
            step.completed_at = datetime.utcnow()
        
        db.commit()
        
        log_job_event(
            str(job_id),
            str(job.document_id),
            "cancel",
            "job_cancelled",
            success=True
        )
        
        return {"message": "Job cancelled successfully"}
        
    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Cancel failed: {str(e)}")


@router.get("/stats", response_model=JobStats)
async def get_job_stats(
    db: Session = Depends(get_db),
):
    """Get job processing statistics."""
    
    try:
        # Get basic counts
        total_jobs = db.query(Job).count()
        
        # Count by status
        status_counts = {}
        for status in JobStatus:
            count = db.query(Job).filter(Job.status == status).count()
            status_counts[status.value] = count
        
        # Count by job type
        job_type_query = db.query(Job.job_type, db.func.count(Job.id)).group_by(Job.job_type).all()
        job_type_counts = {job_type: count for job_type, count in job_type_query}
        
        # Calculate processing time average
        completed_jobs = db.query(Job).filter(Job.status == JobStatus.COMPLETED).all()
        processing_times = []
        
        for job in completed_jobs:
            if job.started_at and job.completed_at:
                duration = (job.completed_at - job.started_at).total_seconds()
                processing_times.append(duration)
        
        average_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
        
        # Calculate success rate
        completed_count = status_counts.get(JobStatus.COMPLETED.value, 0)
        failed_count = status_counts.get(JobStatus.FAILED.value, 0)
        total_finished = completed_count + failed_count
        success_rate = (completed_count / total_finished * 100) if total_finished > 0 else 0
        
        # Current queue size (pending jobs)
        current_queue_size = status_counts.get(JobStatus.PENDING.value, 0)
        
        # Active workers (approximate from running jobs)
        active_workers = status_counts.get(JobStatus.RUNNING.value, 0)
        
        return JobStats(
            total_jobs=total_jobs,
            by_status=status_counts,
            by_job_type=job_type_counts,
            average_processing_time=average_processing_time,
            success_rate=success_rate,
            current_queue_size=current_queue_size,
            active_workers=active_workers,
        )
        
    except Exception as e:
        logger.error(f"Failed to get job stats: {e}")
        raise HTTPException(status_code=500, detail=f"Stats generation failed: {str(e)}")


@router.post("/search", response_model=JobList)
async def search_jobs(
    search_request: JobSearchRequest,
    db: Session = Depends(get_db),
):
    """Advanced job search with multiple filters."""
    
    query = db.query(Job)
    
    # Apply filters
    if search_request.document_id:
        query = query.filter(Job.document_id == search_request.document_id)
    
    if search_request.job_type:
        query = query.filter(Job.job_type == search_request.job_type)
    
    if search_request.status:
        query = query.filter(Job.status == search_request.status)
    
    if search_request.worker_id:
        query = query.filter(Job.worker_id == search_request.worker_id)
    
    if search_request.date_from:
        query = query.filter(Job.created_at >= search_request.date_from)
    
    if search_request.date_to:
        query = query.filter(Job.created_at <= search_request.date_to)
    
    # Get total count
    total = query.count()
    
    # Apply sorting
    sort_column = getattr(Job, search_request.sort_by, Job.created_at)
    if search_request.sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
    
    # Apply pagination
    offset = (search_request.page - 1) * search_request.per_page
    jobs = query.offset(offset).limit(search_request.per_page).all()
    
    # Calculate pages
    pages = (total + search_request.per_page - 1) // search_request.per_page
    
    return JobList(
        jobs=[JobSummary.from_orm(job) for job in jobs],
        total=total,
        page=search_request.page,
        per_page=search_request.per_page,
        pages=pages,
    )