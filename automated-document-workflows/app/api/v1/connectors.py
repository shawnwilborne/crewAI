"""
Connector API endpoints for external services (Shopify, S3, SFTP).
"""

from typing import Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Output
from app.schemas.output import DeliveryRequest, DeliveryResponse
from app.utils.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/status")
async def get_connector_status():
    """Get status of all connectors."""
    
    return {
        "shopify": {
            "enabled": settings.shopify_enabled,
            "configured": bool(settings.shopify_shop and settings.shopify_access_token),
        },
        "s3": {
            "enabled": settings.s3_enabled,
            "configured": bool(settings.aws_access_key_id and settings.aws_secret_access_key and settings.aws_s3_bucket),
        },
        "sftp": {
            "enabled": settings.sftp_enabled,
            "configured": bool(settings.sftp_host and settings.sftp_user),
        },
    }


@router.post("/shopify/upload")
async def upload_to_shopify(
    output_id: UUID,
    request: DeliveryRequest,
    db: Session = Depends(get_db),
):
    """Upload an output file to Shopify."""
    
    if not settings.shopify_enabled:
        raise HTTPException(status_code=400, detail="Shopify connector not enabled")
    
    output = db.query(Output).filter(Output.id == output_id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    
    # TODO: Implement Shopify upload
    # This would use the shopify_client.py service
    
    return DeliveryResponse(
        output_id=output_id,
        target="shopify",
        destination=request.destination or "default",
        status="pending",
        error_message="Shopify upload not implemented yet",
    )


@router.post("/s3/push")
async def push_to_s3(
    output_id: UUID,
    request: DeliveryRequest,
    db: Session = Depends(get_db),
):
    """Push an output file to S3."""
    
    if not settings.s3_enabled:
        raise HTTPException(status_code=400, detail="S3 connector not enabled")
    
    output = db.query(Output).filter(Output.id == output_id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    
    # TODO: Implement S3 upload
    # This would use the s3_client.py service
    
    return DeliveryResponse(
        output_id=output_id,
        target="s3",
        destination=request.destination or settings.aws_s3_bucket,
        status="pending",
        error_message="S3 upload not implemented yet",
    )


@router.post("/sftp/push")
async def push_to_sftp(
    output_id: UUID,
    request: DeliveryRequest,
    db: Session = Depends(get_db),
):
    """Push an output file to SFTP server."""
    
    if not settings.sftp_enabled:
        raise HTTPException(status_code=400, detail="SFTP connector not enabled")
    
    output = db.query(Output).filter(Output.id == output_id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    
    # TODO: Implement SFTP upload
    # This would use the sftp_client.py service
    
    return DeliveryResponse(
        output_id=output_id,
        target="sftp",
        destination=request.destination or "/",
        status="pending",
        error_message="SFTP upload not implemented yet",
    )