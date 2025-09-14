"""
Main document processing pipeline orchestrator.
"""

import os
import time
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import (
    Document, Job, Step, Page, Output, JobStatus, StepStatus, StepType,
    DocumentStatus, DeliveryStatus
)
from app.utils.settings import settings
from app.utils.logging import get_logger, log_job_event
from app.services.baas_client import BaaSClient
from app.services.ocr.ocr_local import LocalOCRProcessor
from app.services.transform.pdf_tools import PDFProcessor
from app.services.transform.docx_writer import DOCXWriter
from app.services.routing.rules_engine import RoutingEngine
from app.services.transform.bates import BatesNumbering
from app.services.transform.renamer import FileRenamer

logger = get_logger(__name__)


class DocumentProcessor:
    """Main document processing pipeline."""
    
    def __init__(self, db: Session):
        self.db = db
        self.baas_client = BaaSClient() if settings.baas_enabled else None
        self.ocr_processor = LocalOCRProcessor()
        self.pdf_processor = PDFProcessor()
        self.docx_writer = DOCXWriter()
        self.routing_engine = RoutingEngine(db)
        self.bates_numbering = BatesNumbering(db)
        self.file_renamer = FileRenamer(db)
    
    def process_job(self, job: Job, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        Process a complete document job through the pipeline.
        
        Args:
            job: Job to process
            progress_callback: Function to call with progress updates
            
        Returns:
            Processing results
        """
        
        logger.info(f"Starting job {job.id} for document {job.document_id}")
        
        try:
            # Get document
            document = self.db.query(Document).filter(Document.id == job.document_id).first()
            if not document:
                raise ValueError(f"Document {job.document_id} not found")
            
            # Update document status
            document.status = DocumentStatus.PROCESSING
            document.processing_started_at = datetime.utcnow()
            self.db.commit()
            
            # Initialize pipeline steps based on job config
            steps = self._create_pipeline_steps(job)
            
            # Execute pipeline steps
            results = {}
            total_steps = len(steps)
            
            for i, step_config in enumerate(steps):
                try:
                    # Update progress
                    progress = (i / total_steps) * 100
                    if progress_callback:
                        progress_callback(progress, step_config["name"])
                    
                    # Execute step
                    step_result = self._execute_step(job, document, step_config)
                    results[step_config["type"]] = step_result
                    
                    logger.info(f"Completed step {step_config['type']} for job {job.id}")
                    
                except Exception as e:
                    logger.error(f"Step {step_config['type']} failed for job {job.id}: {e}")
                    
                    # Check if step is critical
                    if step_config.get("critical", True):
                        raise e
                    else:
                        # Log error and continue
                        results[step_config["type"]] = {"error": str(e), "skipped": True}
            
            # Final progress update
            if progress_callback:
                progress_callback(100, "Completed")
            
            # Update document status
            document.status = DocumentStatus.COMPLETED
            document.processing_completed_at = datetime.utcnow()
            self.db.commit()
            
            log_job_event(
                str(job.id),
                str(job.document_id),
                "complete",
                "job_completed",
                success=True,
                metadata={"steps_completed": len(results)}
            )
            
            return {
                "status": "completed",
                "steps_executed": len(results),
                "results": results,
                "processing_time_seconds": (datetime.utcnow() - document.processing_started_at).total_seconds()
            }
            
        except Exception as e:
            logger.error(f"Job {job.id} processing failed: {e}")
            
            # Update document status
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)
            document.processing_completed_at = datetime.utcnow()
            self.db.commit()
            
            log_job_event(
                str(job.id),
                str(job.document_id),
                "error",
                "job_failed",
                success=False,
                error=str(e)
            )
            
            raise e
    
    def _create_pipeline_steps(self, job: Job) -> list:
        """Create pipeline steps based on job configuration."""
        
        config = job.config or {}
        steps = []
        
        # Step 1: OCR/Text Extraction (if needed)
        if config.get("ocr_enabled", True):
            steps.append({
                "type": StepType.OCR,
                "name": "Text Extraction",
                "config": {
                    "engine": config.get("ocr_engine", "auto"),  # auto, tesseract, baas
                    "language": config.get("ocr_language", "eng"),
                    "dpi": config.get("ocr_dpi", 300),
                },
                "critical": True
            })
        
        # Step 2: Document Conversion
        if config.get("convert_to_docx", True) or config.get("convert_to_searchable_pdf", True):
            steps.append({
                "type": StepType.CONVERT,
                "name": "Document Conversion",
                "config": {
                    "to_docx": config.get("convert_to_docx", True),
                    "to_searchable_pdf": config.get("convert_to_searchable_pdf", True),
                    "preserve_formatting": config.get("preserve_formatting", True),
                },
                "critical": True
            })
        
        # Step 3: Template Application
        if config.get("apply_template", False):
            steps.append({
                "type": StepType.APPLY_TEMPLATE,
                "name": "Apply Template",
                "config": {
                    "template_name": config.get("template_name"),
                    "template_data": config.get("template_data", {}),
                },
                "critical": False
            })
        
        # Step 4: Routing
        if config.get("apply_routing", True):
            steps.append({
                "type": StepType.ROUTE,
                "name": "Document Routing",
                "config": {
                    "rules": config.get("routing_rules"),
                },
                "critical": False
            })
        
        # Step 5: Renaming
        steps.append({
            "type": StepType.RENAME,
            "name": "File Renaming",
            "config": {},
            "critical": False
        })
        
        # Step 6: Bates Numbering
        if config.get("apply_bates", False):
            steps.append({
                "type": StepType.BATES,
                "name": "Bates Numbering",
                "config": {
                    "prefix": config.get("bates_prefix"),
                    "start": config.get("bates_start"),
                    "position": config.get("bates_position", "bottom_right"),
                },
                "critical": False
            })
        
        # Step 7: Delivery
        if config.get("auto_deliver", False):
            steps.append({
                "type": StepType.DELIVER,
                "name": "Document Delivery",
                "config": {
                    "targets": config.get("delivery_targets", []),
                },
                "critical": False
            })
        
        return steps
    
    def _execute_step(self, job: Job, document: Document, step_config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single pipeline step."""
        
        step_type = step_config["type"]
        step_name = step_config["name"]
        config = step_config["config"]
        
        # Create step record
        step = Step(
            job_id=job.id,
            step_type=step_type,
            step_name=step_name,
            sequence_order=len(job.steps) + 1,
            config=config,
            status=StepStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        
        self.db.add(step)
        self.db.commit()
        self.db.refresh(step)
        
        start_time = time.time()
        
        try:
            # Execute step based on type
            if step_type == StepType.OCR:
                result = self._execute_ocr_step(document, config)
            elif step_type == StepType.CONVERT:
                result = self._execute_convert_step(document, config)
            elif step_type == StepType.APPLY_TEMPLATE:
                result = self._execute_template_step(document, config)
            elif step_type == StepType.ROUTE:
                result = self._execute_routing_step(document, config)
            elif step_type == StepType.RENAME:
                result = self._execute_rename_step(document, config)
            elif step_type == StepType.BATES:
                result = self._execute_bates_step(document, config)
            elif step_type == StepType.DELIVER:
                result = self._execute_delivery_step(document, config)
            else:
                raise ValueError(f"Unknown step type: {step_type}")
            
            # Update step status
            step.status = StepStatus.COMPLETED
            step.completed_at = datetime.utcnow()
            step.processing_time_seconds = time.time() - start_time
            step.result = result
            
            self.db.commit()
            
            return result
            
        except Exception as e:
            # Update step status
            step.status = StepStatus.FAILED
            step.completed_at = datetime.utcnow()
            step.processing_time_seconds = time.time() - start_time
            step.error_message = str(e)
            
            self.db.commit()
            
            raise e
    
    def _execute_ocr_step(self, document: Document, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute OCR/text extraction step."""
        
        engine = config.get("engine", "auto")
        
        # Decide on OCR engine
        if engine == "auto":
            if self.baas_client and settings.baas_enabled:
                engine = "baas"
            else:
                engine = "tesseract"
        
        if engine == "baas" and self.baas_client:
            # Use BaaS for OCR
            result = self._process_with_baas(document, config)
        else:
            # Use local OCR
            result = self._process_with_local_ocr(document, config)
        
        # Update document with extracted text
        if result.get("extracted_text"):
            document.extracted_text = result["extracted_text"]
            document.has_text = True
            
        if result.get("language"):
            document.language = result["language"]
            
        if result.get("page_count"):
            document.page_count = result["page_count"]
        
        self.db.commit()
        
        return result
    
    def _process_with_baas(self, document: Document, config: Dict[str, Any]) -> Dict[str, Any]:
        """Process document using BaaS service."""
        
        try:
            # Submit to BaaS
            baas_job = self.baas_client.submit_document(
                document.file_path,
                workflow_id=settings.lv_baas_workflow_id,
                callback_url=f"{settings.api_host}/api/v1/baas/webhook"
            )
            
            # Update document with BaaS job ID
            document.baas_job_id = baas_job["job_id"]
            self.db.commit()
            
            # Wait for completion (with timeout)
            result = self.baas_client.wait_for_completion(
                baas_job["job_id"],
                timeout_seconds=config.get("timeout", 600)
            )
            
            # Process BaaS results
            if result["status"] == "completed":
                return {
                    "engine": "baas",
                    "extracted_text": result.get("extracted_text"),
                    "language": result.get("language"),
                    "confidence_score": result.get("confidence_score"),
                    "page_count": result.get("pages_processed"),
                    "processing_time_ms": result.get("processing_time_ms"),
                    "entities": result.get("entities"),
                    "tables": result.get("tables"),
                    "fields": result.get("fields"),
                }
            else:
                raise Exception(f"BaaS processing failed: {result.get('error_message')}")
                
        except Exception as e:
            logger.warning(f"BaaS processing failed, falling back to local: {e}")
            return self._process_with_local_ocr(document, config)
    
    def _process_with_local_ocr(self, document: Document, config: Dict[str, Any]) -> Dict[str, Any]:
        """Process document using local OCR."""
        
        return self.ocr_processor.process_document(
            document.file_path,
            language=config.get("language", "eng"),
            dpi=config.get("dpi", 300)
        )
    
    def _execute_convert_step(self, document: Document, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute document conversion step."""
        
        results = {}
        
        # Convert to searchable PDF if requested
        if config.get("to_searchable_pdf", True):
            searchable_pdf = self.pdf_processor.make_searchable(
                document.file_path,
                output_dir=settings.output_dir
            )
            
            if searchable_pdf:
                # Create output record
                output = Output(
                    document_id=document.id,
                    filename=os.path.basename(searchable_pdf),
                    file_path=searchable_pdf,
                    file_size=os.path.getsize(searchable_pdf),
                    mime_type="application/pdf",
                    format_type="pdf",
                    output_type="searchable_pdf",
                    description="Searchable PDF with OCR text layer",
                )
                
                self.db.add(output)
                results["searchable_pdf"] = searchable_pdf
        
        # Convert to DOCX if requested
        if config.get("to_docx", True):
            docx_file = self.docx_writer.convert_from_document(
                document.file_path,
                document.extracted_text,
                output_dir=settings.output_dir
            )
            
            if docx_file:
                # Create output record
                output = Output(
                    document_id=document.id,
                    filename=os.path.basename(docx_file),
                    file_path=docx_file,
                    file_size=os.path.getsize(docx_file),
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    format_type="docx",
                    output_type="converted_docx",
                    description="DOCX conversion of original document",
                )
                
                self.db.add(output)
                results["docx_file"] = docx_file
        
        self.db.commit()
        
        return results
    
    def _execute_template_step(self, document: Document, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute template application step."""
        
        template_name = config.get("template_name")
        template_data = config.get("template_data", {})
        
        if not template_name:
            return {"skipped": True, "reason": "No template specified"}
        
        # TODO: Implement template application
        # This would use the template engine to apply templates
        
        return {
            "template_applied": template_name,
            "data_used": template_data,
            "note": "Template application not implemented yet"
        }
    
    def _execute_routing_step(self, document: Document, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute document routing step."""
        
        return self.routing_engine.apply_routing_rules(
            document,
            rule_names=config.get("rules")
        )
    
    def _execute_rename_step(self, document: Document, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute file renaming step."""
        
        return self.file_renamer.apply_renaming(document)
    
    def _execute_bates_step(self, document: Document, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Bates numbering step."""
        
        return self.bates_numbering.apply_bates_numbering(
            document,
            prefix=config.get("prefix"),
            start_number=config.get("start"),
            position=config.get("position", "bottom_right")
        )
    
    def _execute_delivery_step(self, document: Document, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute document delivery step."""
        
        targets = config.get("targets", [])
        
        if not targets:
            return {"skipped": True, "reason": "No delivery targets specified"}
        
        # TODO: Implement delivery logic
        # This would use the connector services to deliver to various targets
        
        return {
            "targets": targets,
            "note": "Delivery not implemented yet"
        }