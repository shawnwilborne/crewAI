"""
Output management API endpoints.
"""

import os
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc

from app.db.database import get_db
from app.db.models import Output, Document
from app.schemas.output import (
    Output as OutputSchema,
    OutputSummary,
    OutputList,
    OutputDownloadResponse,
    OutputStats,
    OutputSearchRequest,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/", response_model=OutputList)
async def list_outputs(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    document_id: Optional[UUID] = Query(None, description="Filter by document ID"),
    output_type: Optional[str] = Query(None, description="Filter by output type"),
    format_type: Optional[str] = Query(None, description="Filter by format type"),
    db: Session = Depends(get_db),
):
    """List outputs with filtering and pagination."""
    
    query = db.query(Output)
    
    # Apply filters
    if document_id:
        query = query.filter(Output.document_id == document_id)
    
    if output_type:
        query = query.filter(Output.output_type == output_type)
    
    if format_type:
        query = query.filter(Output.format_type == format_type)
    
    # Get total count
    total = query.count()
    
    # Apply sorting and pagination
    offset = (page - 1) * per_page
    outputs = query.order_by(desc(Output.created_at)).offset(offset).limit(per_page).all()
    
    pages = (total + per_page - 1) // per_page
    
    return OutputList(
        outputs=[OutputSummary.from_orm(output) for output in outputs],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get("/{output_id}", response_model=OutputSchema)
async def get_output(
    output_id: UUID,
    db: Session = Depends(get_db),
):
    """Get output details by ID."""
    
    output = db.query(Output).filter(Output.id == output_id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    
    return OutputSchema.from_orm(output)


@router.get("/{output_id}/download")
async def download_output(
    output_id: UUID,
    db: Session = Depends(get_db),
):
    """Download an output file."""
    
    output = db.query(Output).filter(Output.id == output_id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    
    if not os.path.exists(output.file_path):
        raise HTTPException(status_code=404, detail="Output file not found on disk")
    
    return FileResponse(
        path=output.file_path,
        filename=output.filename,
        media_type=output.mime_type,
    )


@router.delete("/{output_id}")
async def delete_output(
    output_id: UUID,
    db: Session = Depends(get_db),
):
    """Delete an output and its file."""
    
    output = db.query(Output).filter(Output.id == output_id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    
    try:
        # Delete physical file
        if os.path.exists(output.file_path):
            os.remove(output.file_path)
        
        # Delete from database
        db.delete(output)
        db.commit()
        
        return {"message": "Output deleted successfully"}
        
    except Exception as e:
        logger.error(f"Failed to delete output {output_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/stats", response_model=OutputStats)
async def get_output_stats(
    db: Session = Depends(get_db),
):
    """Get output statistics."""
    
    try:
        total_outputs = db.query(Output).count()
        
        # Count by type
        type_query = db.query(Output.output_type, db.func.count(Output.id)).group_by(Output.output_type).all()
        type_counts = {output_type: count for output_type, count in type_query}
        
        # Count by format
        format_query = db.query(Output.format_type, db.func.count(Output.id)).group_by(Output.format_type).all()
        format_counts = {format_type: count for format_type, count in format_query}
        
        # Count by delivery status
        status_query = db.query(Output.delivery_status, db.func.count(Output.id)).group_by(Output.delivery_status).all()
        status_counts = {status: count for status, count in status_query}
        
        # Size statistics
        size_stats = db.query(
            db.func.sum(Output.file_size),
            db.func.avg(Output.file_size),
        ).first()
        
        total_size = int(size_stats[0]) if size_stats[0] else 0
        avg_size = float(size_stats[1]) if size_stats[1] else 0
        
        return OutputStats(
            total_outputs=total_outputs,
            by_type=type_counts,
            by_format=format_counts,
            by_delivery_status=status_counts,
            total_size_bytes=total_size,
            average_size_bytes=avg_size,
        )
        
    except Exception as e:
        logger.error(f"Failed to get output stats: {e}")
        raise HTTPException(status_code=500, detail=f"Stats generation failed: {str(e)}")