"""Database models for Website Builder."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class WebsiteStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SUSPENDED = "suspended"


class TemplateType(str, Enum):
    HAIRDRESSER = "hairdresser"
    MASSAGE = "massage"
    BEAUTY_SALON = "beauty_salon"


class WebsiteBase(BaseModel):
    """Base website model."""
    name: str = Field(..., min_length=1, max_length=255)
    tenant_id: str
    template_type: TemplateType
    custom_domain: Optional[str] = None
    ssl_enabled: bool = False
    status: WebsiteStatus = WebsiteStatus.DRAFT


class WebsiteCreate(WebsiteBase):
    """Create website request."""
    pass


class WebsiteUpdate(BaseModel):
    """Update website request."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    custom_domain: Optional[str] = None
    ssl_enabled: Optional[bool] = None
    status: Optional[WebsiteStatus] = None


class Section(BaseModel):
    """Page section model."""
    id: str
    type: str  # hero, services, gallery, contact, testimonials, footer
    order: int
    content: dict = {}
    styles: dict = {}


class Page(BaseModel):
    """Page model."""
    id: str
    website_id: str
    title: str
    slug: str
    sections: List[Section] = []
    is_home: bool = False
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None


class PageCreate(BaseModel):
    """Create page request."""
    title: str
    slug: str
    is_home: bool = False


class PageUpdate(BaseModel):
    """Update page request."""
    title: Optional[str] = None
    slug: Optional[str] = None
    sections: Optional[List[Section]] = None
    is_home: Optional[bool] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None


class Website(WebsiteBase):
    """Full website model."""
    id: str
    pages: List[Page] = []
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Template(BaseModel):
    """Template model."""
    id: str
    name: str
    type: TemplateType
    description: str
    thumbnail_url: Optional[str] = None
    sections: List[dict] = []
    variables: List[dict] = []  # Customizable template variables


class DomainConfig(BaseModel):
    """Custom domain configuration."""
    domain: str
    ssl_cert_arn: Optional[str] = None
    ssl_status: str = "pending"  # pending, provisioning, active, failed
    cloudfront_arn: Optional[str] = None


class BookingWidgetConfig(BaseModel):
    """Booking widget configuration."""
    enabled: bool = True
    position: str = "bottom-right"  # bottom-right, bottom-left, inline
    theme: str = "light"  # light, dark
    primary_color: str = "#1E40AF"
    company_name: Optional[str] = None
    service_ids: List[str] = []