"""
Pydantic schemas for routing-related API models.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, validator


class RoutingCondition(BaseModel):
    """Schema for routing rule conditions."""
    type: str = Field(..., description="Condition type (filename_regex, keywords, mime_type, etc.)")
    value: Any = Field(..., description="Condition value")
    operator: Optional[str] = Field("equals", description="Comparison operator")
    case_sensitive: bool = Field(False, description="Case sensitive matching")


class RoutingAction(BaseModel):
    """Schema for routing rule actions."""
    type: str = Field(..., description="Action type (move, copy, rename, etc.)")
    destination: Optional[str] = Field(None, description="Destination path/target")
    rename_template: Optional[str] = Field(None, description="Rename template with placeholders")
    bates_prefix: Optional[str] = Field(None, description="Bates number prefix")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class RoutingRule(BaseModel):
    """Schema for routing rules."""
    name: str = Field(..., description="Rule name (unique identifier)")
    description: Optional[str] = Field(None, description="Rule description")
    conditions: List[RoutingCondition] = Field(..., description="List of conditions (AND logic)")
    actions: List[RoutingAction] = Field(..., description="List of actions to execute")
    priority: int = Field(0, description="Rule priority (higher = more priority)")
    enabled: bool = Field(True, description="Whether rule is active")


class RoutingRuleCreate(RoutingRule):
    """Schema for creating a routing rule."""
    pass


class RoutingRuleUpdate(BaseModel):
    """Schema for updating a routing rule."""
    description: Optional[str] = None
    conditions: Optional[List[RoutingCondition]] = None
    actions: Optional[List[RoutingAction]] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


class RoutingRuleResponse(RoutingRule):
    """Schema for routing rule response."""
    id: UUID
    matched_count: int = 0
    last_matched_at: Optional[datetime] = None
    source_file: Optional[str] = None
    source_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RouteBase(BaseModel):
    """Base route schema."""
    rule_name: str = Field(..., description="Name of the matched rule")
    matched_conditions: Optional[Dict[str, Any]] = Field(None, description="Which conditions matched")
    destination: str = Field(..., description="Destination path/target")
    rename_template: Optional[str] = Field(None, description="Rename template")
    final_filename: Optional[str] = Field(None, description="Final filename after renaming")


class RouteCreate(RouteBase):
    """Schema for creating a route."""
    document_id: UUID = Field(..., description="Document ID")


class RouteUpdate(BaseModel):
    """Schema for updating a route."""
    applied: Optional[bool] = None
    final_filename: Optional[str] = None
    error_message: Optional[str] = None


class Route(RouteBase):
    """Schema for route response."""
    id: UUID
    document_id: UUID
    applied: bool = False
    applied_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoutingTestRequest(BaseModel):
    """Schema for testing routing rules."""
    filename: Optional[str] = Field(None, description="Test filename")
    mime_type: Optional[str] = Field(None, description="Test MIME type")
    content: Optional[str] = Field(None, description="Test content for keyword matching")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional test metadata")
    rules: Optional[List[str]] = Field(None, description="Specific rules to test (default: all)")


class RoutingTestResult(BaseModel):
    """Result of routing rule testing."""
    rule_name: str
    matched: bool
    matched_conditions: List[str] = []
    actions: List[RoutingAction] = []
    destination: Optional[str] = None
    final_filename: Optional[str] = None
    priority: int = 0


class RoutingTestResponse(BaseModel):
    """Response for routing rule testing."""
    test_input: RoutingTestRequest
    results: List[RoutingTestResult]
    total_rules: int
    matched_rules: int
    execution_time_ms: float


class RoutingStats(BaseModel):
    """Routing system statistics."""
    total_rules: int
    active_rules: int
    total_routes: int
    successful_routes: int
    failed_routes: int
    by_rule: Dict[str, int]  # Routes by rule name
    by_destination: Dict[str, int]  # Routes by destination
    average_processing_time_ms: float


class BulkRoutingRequest(BaseModel):
    """Schema for bulk routing operations."""
    document_ids: List[UUID] = Field(..., description="List of document IDs")
    rule_names: Optional[List[str]] = Field(None, description="Specific rules to apply")
    dry_run: bool = Field(True, description="Test mode - don't actually apply routes")
    force_reprocess: bool = Field(False, description="Reprocess already routed documents")


class BulkRoutingResponse(BaseModel):
    """Response for bulk routing operations."""
    total_documents: int
    processed: int
    successful: int
    failed: int
    skipped: int
    results: List[Dict[str, Any]]
    dry_run: bool
    execution_time_ms: float


class RenameTemplate(BaseModel):
    """Schema for rename template definitions."""
    name: str = Field(..., description="Template name")
    pattern: str = Field(..., description="Rename pattern with placeholders")
    description: Optional[str] = Field(None, description="Template description")
    
    # Available placeholders
    placeholders: List[str] = Field(
        default=[
            "date_yyyy_mm_dd",
            "date_yyyy",
            "date_mm",
            "date_dd", 
            "time_hh_mm_ss",
            "doc_type",
            "filename",
            "extension",
            "counter",
            "bates_number",
            "page_count",
            "file_size_mb"
        ],
        description="Available placeholders for this template"
    )

    @validator("pattern")
    def validate_pattern(cls, v):
        """Validate that pattern contains valid placeholders."""
        import re
        placeholders = re.findall(r'\{([^}]+)\}', v)
        valid_placeholders = [
            "date_yyyy_mm_dd", "date_yyyy", "date_mm", "date_dd",
            "time_hh_mm_ss", "doc_type", "filename", "extension",
            "counter", "bates_number", "page_count", "file_size_mb"
        ]
        
        for placeholder in placeholders:
            # Handle counter with padding like {counter:6}
            base_placeholder = placeholder.split(':')[0]
            if base_placeholder not in valid_placeholders:
                raise ValueError(f"Invalid placeholder: {placeholder}")
        
        return v


class RenamePreviewRequest(BaseModel):
    """Schema for previewing rename operations."""
    document_ids: List[UUID] = Field(..., description="List of document IDs")
    template: str = Field(..., description="Rename template pattern")
    counter_start: int = Field(1, description="Starting counter value")
    counter_padding: int = Field(6, description="Counter padding (zero-fill)")


class RenamePreviewResult(BaseModel):
    """Result of rename preview."""
    document_id: UUID
    original_filename: str
    new_filename: str
    conflicts: List[str] = []  # Any naming conflicts
    metadata: Dict[str, Any] = {}  # Resolved placeholder values


class RenamePreviewResponse(BaseModel):
    """Response for rename preview."""
    results: List[RenamePreviewResult]
    total_documents: int
    conflicts: int
    duplicates: int
    template_used: str