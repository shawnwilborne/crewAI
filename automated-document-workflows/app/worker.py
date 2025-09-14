"""
Celery worker configuration and tasks for background processing.
"""

import os
import sys
from typing import Dict, Any

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

from app.utils.settings import settings
from app.utils.logging import setup_logging, get_logger

# Setup logging for worker
setup_logging()
logger = get_logger(__name__)

# Create Celery app
celery_app = Celery(
    "document-processor",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker"]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.celery_task_timeout,
    task_soft_time_limit=settings.celery_task_timeout - 60,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=50,
)


@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Handle worker ready event."""
    logger.info(f"Worker {sender.hostname} is ready")


@worker_shutdown.connect  
def worker_shutdown_handler(sender=None, **kwargs):
    """Handle worker shutdown event."""
    logger.info(f"Worker {sender.hostname} is shutting down")


@celery_app.task(bind=True, name="process_document")
def process_document_task(self, job_id: str) -> Dict[str, Any]:
    """
    Process a document job in the background.
    
    Args:
        job_id: UUID of the job to process
        
    Returns:
        Processing results
    """
    
    from app.services.pipeline import DocumentProcessor
    from app.db.database import SessionLocal
    from app.db.models import Job, JobStatus
    
    db = SessionLocal()
    
    try:
        # Get job from database
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        # Update job status
        job.status = JobStatus.RUNNING
        job.worker_id = self.request.id
        db.commit()
        
        logger.info(f"Starting processing for job {job_id}")
        
        # Initialize document processor
        processor = DocumentProcessor(db)
        
        # Update task progress callback
        def progress_callback(progress: float, message: str = None):
            job.progress = progress
            if message:
                job.current_step = message
            db.commit()
            
            # Update Celery task state
            self.update_state(
                state="PROGRESS",
                meta={"progress": progress, "message": message}
            )
        
        # Process the document
        result = processor.process_job(job, progress_callback)
        
        # Update job with results
        job.status = JobStatus.COMPLETED
        job.progress = 100.0
        job.result = result
        db.commit()
        
        logger.info(f"Completed processing for job {job_id}")
        
        return {
            "job_id": job_id,
            "status": "completed",
            "result": result
        }
        
    except Exception as exc:
        logger.error(f"Job {job_id} failed: {exc}")
        
        # Update job status
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.retry_count = getattr(job, 'retry_count', 0) + 1
            db.commit()
        
        # Retry if under retry limit
        if getattr(job, 'retry_count', 0) < getattr(job, 'max_retries', 3):
            logger.info(f"Retrying job {job_id}, attempt {job.retry_count + 1}")
            raise self.retry(exc=exc, countdown=60, max_retries=job.max_retries)
        
        # Final failure
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(exc)
        }
        
    finally:
        db.close()


@celery_app.task(name="cleanup_temp_files")
def cleanup_temp_files_task() -> Dict[str, Any]:
    """
    Clean up temporary files older than configured threshold.
    
    Returns:
        Cleanup results
    """
    
    import time
    from pathlib import Path
    
    try:
        temp_dir = Path(settings.temp_upload_dir)
        cleanup_threshold = settings.cleanup_temp_files_hours * 3600  # Convert to seconds
        current_time = time.time()
        
        if not temp_dir.exists():
            return {"cleaned_files": 0, "error": "Temp directory does not exist"}
        
        cleaned_files = 0
        total_size = 0
        
        for file_path in temp_dir.iterdir():
            if file_path.is_file():
                # Check file age
                file_age = current_time - file_path.stat().st_mtime
                
                if file_age > cleanup_threshold:
                    try:
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        cleaned_files += 1
                        total_size += file_size
                        logger.debug(f"Cleaned up temp file: {file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to clean temp file {file_path}: {e}")
        
        logger.info(f"Cleaned up {cleaned_files} temp files, freed {total_size} bytes")
        
        return {
            "cleaned_files": cleaned_files,
            "total_size_freed": total_size,
            "cleanup_threshold_hours": settings.cleanup_temp_files_hours
        }
        
    except Exception as e:
        logger.error(f"Temp file cleanup failed: {e}")
        return {"cleaned_files": 0, "error": str(e)}


@celery_app.task(name="health_check")
def health_check_task() -> Dict[str, Any]:
    """
    Health check task for monitoring worker status.
    
    Returns:
        Health check results
    """
    
    import psutil
    
    try:
        # Get system info
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "memory_usage": {
                "total": memory.total,
                "available": memory.available,
                "percent": memory.percent
            },
            "disk_usage": {
                "total": disk.total,
                "free": disk.free,
                "percent": (disk.used / disk.total) * 100
            },
            "settings": {
                "baas_enabled": settings.baas_enabled,
                "temp_dir": settings.temp_upload_dir,
                "output_dir": settings.output_dir
            }
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy", 
            "error": str(e),
            "timestamp": time.time()
        }


@celery_app.task(name="process_batch")
def process_batch_task(document_ids: list, config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Process multiple documents in batch.
    
    Args:
        document_ids: List of document IDs to process
        config: Batch processing configuration
        
    Returns:
        Batch processing results
    """
    
    from app.db.database import SessionLocal
    from app.db.models import Document, Job, JobStatus
    
    db = SessionLocal()
    
    try:
        results = []
        successful = 0
        failed = 0
        
        for doc_id in document_ids:
            try:
                # Create job for document
                job = Job(
                    document_id=doc_id,
                    job_type="batch_process",
                    config=config or {},
                    status=JobStatus.PENDING
                )
                
                db.add(job)
                db.commit()
                db.refresh(job)
                
                # Process immediately (could be changed to queue separately)
                job_result = process_document_task.apply(args=[str(job.id)])
                
                if job_result.successful():
                    successful += 1
                    results.append({
                        "document_id": doc_id,
                        "job_id": str(job.id),
                        "status": "completed"
                    })
                else:
                    failed += 1
                    results.append({
                        "document_id": doc_id,
                        "job_id": str(job.id),
                        "status": "failed",
                        "error": str(job_result.result)
                    })
                    
            except Exception as e:
                failed += 1
                results.append({
                    "document_id": doc_id,
                    "status": "failed", 
                    "error": str(e)
                })
        
        logger.info(f"Batch processing completed: {successful} successful, {failed} failed")
        
        return {
            "total": len(document_ids),
            "successful": successful,
            "failed": failed,
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        return {
            "total": len(document_ids),
            "successful": 0,
            "failed": len(document_ids),
            "error": str(e),
            "results": []
        }
        
    finally:
        db.close()


# Periodic tasks
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'cleanup-temp-files': {
        'task': 'cleanup_temp_files',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'health-check': {
        'task': 'health_check', 
        'schedule': 300.0,  # Every 5 minutes
    },
}


if __name__ == "__main__":
    """Run worker directly."""
    celery_app.start()