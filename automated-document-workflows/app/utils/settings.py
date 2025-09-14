"""
Application settings and configuration management.
"""

import os
from typing import List, Optional, Union
from pydantic import BaseSettings, Field, validator
from enum import Enum


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application
    app_name: str = Field(default="Automated Document Workflows")
    version: str = Field(default="1.0.0")
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    debug: bool = Field(default=True)
    secret_key: str = Field(default="change-me-in-production")
    
    # API Configuration
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_workers: int = Field(default=1)
    cors_origins: List[str] = Field(default=["*"])
    
    # Database
    database_url: str = Field(default="sqlite:///./app.db")
    
    # Redis/Celery
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: Optional[str] = None
    celery_result_backend: Optional[str] = None
    celery_task_timeout: int = Field(default=3600)
    
    # File Processing
    max_file_size: str = Field(default="100MB")
    allowed_extensions: List[str] = Field(default=["pdf", "jpg", "jpeg", "png", "tiff", "docx"])
    temp_upload_dir: str = Field(default="./temp")
    output_dir: str = Field(default="./outputs")
    template_dir: str = Field(default="./templates")
    rules_dir: str = Field(default="./rules")
    quarantine_dir: str = Field(default="./quarantine")
    
    # Lid Vizion BaaS Integration
    lv_baas_api_key: Optional[str] = Field(default=None)
    lv_baas_workflow_id: Optional[str] = Field(default=None)
    lv_baas_base_url: str = Field(default="https://api.lidvizion.com/v1")
    
    # Shopify Integration
    shopify_shop: Optional[str] = Field(default=None)
    shopify_access_token: Optional[str] = Field(default=None)
    
    # AWS S3 Integration
    aws_access_key_id: Optional[str] = Field(default=None)
    aws_secret_access_key: Optional[str] = Field(default=None)
    aws_s3_bucket: Optional[str] = Field(default=None)
    aws_region: str = Field(default="us-west-2")
    
    # SFTP Integration
    sftp_host: Optional[str] = Field(default=None)
    sftp_port: int = Field(default=22)
    sftp_user: Optional[str] = Field(default=None)
    sftp_password: Optional[str] = Field(default=None)
    sftp_private_key_path: Optional[str] = Field(default=None)
    
    # OCR Configuration
    tesseract_cmd: str = Field(default="tesseract")
    ocrmypdf_timeout: int = Field(default=300)
    ocr_language: str = Field(default="eng")
    ocr_dpi: int = Field(default=300)
    
    # Bates Numbering
    bates_default_prefix: str = Field(default="BATES")
    bates_padding: int = Field(default=6)
    
    # Security & Privacy
    mask_pii: bool = Field(default=True)
    max_pages_per_document: int = Field(default=1000)
    
    # Performance
    max_concurrent_jobs: int = Field(default=5)
    cleanup_temp_files_hours: int = Field(default=24)
    
    # Logging
    log_level: str = Field(default="INFO")
    
    @validator("celery_broker_url", pre=True, always=True)
    def set_celery_broker(cls, v, values):
        return v or values.get("redis_url")
    
    @validator("celery_result_backend", pre=True, always=True)
    def set_celery_result_backend(cls, v, values):
        return v or values.get("redis_url")
    
    @validator("debug", pre=True, always=True)
    def set_debug(cls, v, values):
        env = values.get("environment")
        if env == Environment.PRODUCTION:
            return False
        return v
    
    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("allowed_extensions", pre=True)
    def parse_extensions(cls, v):
        if isinstance(v, str):
            return [ext.strip().lower() for ext in v.split(",")]
        return v
    
    def get_max_file_size_bytes(self) -> int:
        """Convert max file size string to bytes."""
        size_str = self.max_file_size.upper()
        if size_str.endswith("GB"):
            return int(float(size_str[:-2]) * 1024 * 1024 * 1024)
        elif size_str.endswith("MB"):
            return int(float(size_str[:-2]) * 1024 * 1024)
        elif size_str.endswith("KB"):
            return int(float(size_str[:-2]) * 1024)
        else:
            return int(size_str)
    
    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION
    
    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT
    
    @property
    def baas_enabled(self) -> bool:
        """Check if BaaS integration is enabled."""
        return bool(self.lv_baas_api_key and self.lv_baas_workflow_id)
    
    @property
    def shopify_enabled(self) -> bool:
        """Check if Shopify integration is enabled."""
        return bool(self.shopify_shop and self.shopify_access_token)
    
    @property
    def s3_enabled(self) -> bool:
        """Check if S3 integration is enabled."""
        return bool(self.aws_access_key_id and self.aws_secret_access_key and self.aws_s3_bucket)
    
    @property
    def sftp_enabled(self) -> bool:
        """Check if SFTP integration is enabled."""
        return bool(self.sftp_host and self.sftp_user and (self.sftp_password or self.sftp_private_key_path))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()