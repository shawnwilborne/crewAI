"""
Lid Vizion BaaS (Backend as a Service) client integration.
"""

import time
import requests
from typing import Dict, Any, Optional
from pathlib import Path

from app.utils.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class BaaSClient:
    """Client for Lid Vizion BaaS document processing service."""
    
    def __init__(self):
        self.api_key = settings.lv_baas_api_key
        self.base_url = settings.lv_baas_base_url
        self.default_workflow_id = settings.lv_baas_workflow_id
        self.timeout = 30
        
        if not self.api_key or not self.default_workflow_id:
            logger.warning("BaaS API key or workflow ID not configured")
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get HTTP headers for BaaS requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AutomatedDocumentWorkflows/1.0"
        }
    
    def submit_document(
        self,
        file_path: str,
        workflow_id: Optional[str] = None,
        callback_url: Optional[str] = None,
        priority: int = 0,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submit a document for BaaS processing.
        
        Args:
            file_path: Path to document file
            workflow_id: BaaS workflow ID (uses default if not provided)
            callback_url: Webhook callback URL for status updates
            priority: Processing priority (higher = more priority)
            config: Additional processing configuration
            
        Returns:
            BaaS job submission response
        """
        
        workflow_id = workflow_id or self.default_workflow_id
        
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Document file not found: {file_path}")
        
        url = f"{self.base_url}/workflows/{workflow_id}/run"
        
        # Prepare request payload
        payload = {
            "priority": priority,
            "config": config or {},
        }
        
        if callback_url:
            payload["callback_url"] = callback_url
        
        try:
            # Upload file and submit job
            with open(file_path, 'rb') as file:
                files = {
                    "file": (Path(file_path).name, file, self._get_mime_type(file_path))
                }
                
                data = {
                    "payload": self._json_dumps(payload)
                }
                
                # Use multipart headers for file upload
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": "AutomatedDocumentWorkflows/1.0"
                }
                
                logger.info(f"Submitting document to BaaS: {Path(file_path).name}")
                
                response = requests.post(
                    url,
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=self.timeout
                )
                
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"BaaS job submitted: {result.get('job_id')}")
                
                return {
                    "job_id": result["job_id"],
                    "status": result.get("status", "submitted"),
                    "estimated_completion": result.get("estimated_completion"),
                    "webhook_url": result.get("webhook_url"),
                    "created_at": result.get("created_at")
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"BaaS submission failed: {e}")
            
            # Check for specific error conditions
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 401:
                    raise Exception("BaaS authentication failed - check API key")
                elif e.response.status_code == 404:
                    raise Exception(f"BaaS workflow not found: {workflow_id}")
                elif e.response.status_code == 429:
                    raise Exception("BaaS rate limit exceeded - please retry later")
                else:
                    error_detail = e.response.text if e.response.text else str(e)
                    raise Exception(f"BaaS submission failed: {error_detail}")
            else:
                raise Exception(f"BaaS connection failed: {str(e)}")
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get the status of a BaaS job.
        
        Args:
            job_id: BaaS job identifier
            
        Returns:
            Job status information
        """
        
        url = f"{self.base_url}/jobs/{job_id}"
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            result = response.json()
            
            return {
                "job_id": result["job_id"],
                "status": result["status"],
                "progress": result.get("progress"),
                "current_step": result.get("current_step"),
                "error_message": result.get("error_message"),
                "result": result.get("result"),
                "created_at": result.get("created_at"),
                "updated_at": result.get("updated_at"),
                "completed_at": result.get("completed_at")
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"BaaS status check failed: {e}")
            raise Exception(f"Failed to get job status: {str(e)}")
    
    def wait_for_completion(
        self,
        job_id: str,
        timeout_seconds: int = 600,
        poll_interval: int = 10
    ) -> Dict[str, Any]:
        """
        Wait for a BaaS job to complete.
        
        Args:
            job_id: BaaS job identifier
            timeout_seconds: Maximum time to wait
            poll_interval: Seconds between status checks
            
        Returns:
            Final job result
        """
        
        start_time = time.time()
        
        logger.info(f"Waiting for BaaS job completion: {job_id}")
        
        while time.time() - start_time < timeout_seconds:
            try:
                status = self.get_job_status(job_id)
                
                if status["status"] in ["completed", "success"]:
                    logger.info(f"BaaS job completed: {job_id}")
                    return status
                elif status["status"] in ["failed", "error", "cancelled"]:
                    error_msg = status.get("error_message", "Job failed")
                    logger.error(f"BaaS job failed: {job_id} - {error_msg}")
                    raise Exception(f"BaaS job failed: {error_msg}")
                
                # Job is still processing
                progress = status.get("progress", 0)
                current_step = status.get("current_step", "processing")
                logger.debug(f"BaaS job {job_id} progress: {progress}% ({current_step})")
                
                time.sleep(poll_interval)
                
            except Exception as e:
                if "BaaS job failed" in str(e):
                    raise e  # Re-raise job failure errors
                
                # Log other errors but continue polling
                logger.warning(f"Error checking BaaS job status: {e}")
                time.sleep(poll_interval)
        
        # Timeout reached
        raise Exception(f"BaaS job timeout after {timeout_seconds} seconds: {job_id}")
    
    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """
        Cancel a BaaS job.
        
        Args:
            job_id: BaaS job identifier
            
        Returns:
            Cancellation response
        """
        
        url = f"{self.base_url}/jobs/{job_id}/cancel"
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"BaaS job cancelled: {job_id}")
            
            return {
                "job_id": job_id,
                "status": "cancelled",
                "message": result.get("message", "Job cancelled successfully")
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"BaaS job cancellation failed: {e}")
            raise Exception(f"Failed to cancel job: {str(e)}")
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check BaaS service health and connectivity.
        
        Returns:
            Health check results
        """
        
        start_time = time.time()
        
        try:
            # Check service availability
            url = f"{self.base_url}/health"
            
            response = requests.get(
                url,
                headers=self.headers,
                timeout=10
            )
            
            response.raise_for_status()
            response_time = (time.time() - start_time) * 1000
            
            # Verify workflow exists
            workflow_url = f"{self.base_url}/workflows/{self.default_workflow_id}"
            workflow_response = requests.get(
                workflow_url,
                headers=self.headers,
                timeout=5
            )
            
            workflow_exists = workflow_response.status_code == 200
            
            return {
                "service_available": True,
                "api_key_valid": True,
                "workflow_exists": workflow_exists,
                "response_time_ms": response_time,
                "last_checked": time.time(),
                "error_message": None
            }
            
        except requests.exceptions.RequestException as e:
            error_message = str(e)
            
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 401:
                    error_message = "Invalid API key"
                elif e.response.status_code == 403:
                    error_message = "API key lacks required permissions"
            
            return {
                "service_available": False,
                "api_key_valid": False,
                "workflow_exists": False,
                "response_time_ms": (time.time() - start_time) * 1000,
                "last_checked": time.time(),
                "error_message": error_message
            }
    
    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type for file."""
        import mimetypes
        
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or 'application/octet-stream'
    
    def _json_dumps(self, obj: Any) -> str:
        """JSON encode object."""
        import json
        return json.dumps(obj, ensure_ascii=False)