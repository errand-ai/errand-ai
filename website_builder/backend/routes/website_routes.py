"""Website Builder API Routes."""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from .models.schemas import (
    Website, WebsiteCreate, WebsiteUpdate, WebsiteStatus,
    Template, TemplateType, Page, PageCreate, PageUpdate,
    Section, DomainConfig, BookingWidgetConfig
)

router = APIRouter(prefix="/api/websites", tags=["websites"])

# In-memory storage (replace with database in production)
websites_db: dict[str, Website] = {}
templates_db: dict[str, Template] = {}

# Initialize default templates
DEFAULT_TEMPLATES = [
    Template(
        id="tpl-hairdresser-001",
        name="Classic Cuts & Styles",
        type=TemplateType.HAIRDRESSER,
        description="Elegant hairdresser template with service showcase and booking integration.",
        thumbnail_url="/templates/hairdresser/thumbnail.jpg",
        sections=[
            {"type": "hero", "name": "Hero Section", "required": True},
            {"type": "services", "name": "Services Grid", "required": True},
            {"type": "gallery", "name": "Style Gallery", "required": False},
            {"type": "testimonials", "name": "Client Reviews", "required": False},
            {"type": "contact", "name": "Contact Form", "required": True},
            {"type": "footer", "name": "Footer", "required": True}
        ],
        variables=[
            {"name": "business_name", "type": "string", "required": True},
            {"name": "tagline", "type": "string", "required": False},
            {"name": "phone", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": True},
            {"name": "address", "type": "string", "required": True},
            {"name": "opening_hours", "type": "object", "required": False}
        ]
    ),
    Template(
        id="tpl-massage-001",
        name="Relax & Wellness Spa",
        type=TemplateType.MASSAGE,
        description="Calming massage therapy template with treatment packages and online booking.",
        thumbnail_url="/templates/massage/thumbnail.jpg",
        sections=[
            {"type": "hero", "name": "Hero Section", "required": True},
            {"type": "treatments", "name": "Treatment Menu", "required": True},
            {"type": "pricing", "name": "Pricing Table", "required": True},
            {"type": "about", "name": "About Section", "required": False},
            {"type": "contact", "name": "Contact Section", "required": True},
            {"type": "footer", "name": "Footer", "required": True}
        ],
        variables=[
            {"name": "business_name", "type": "string", "required": True},
            {"name": "tagline", "type": "string", "required": False},
            {"name": "phone", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": True},
            {"name": "address", "type": "string", "required": True},
            {"name": "specialties", "type": "array", "required": False}
        ]
    ),
    Template(
        id="tpl-beauty-salon-001",
        name="Glamour Beauty Studio",
        type=TemplateType.BEAUTY_SALON,
        description="Modern beauty salon template with makeup, nails, and aesthetic services.",
        thumbnail_url="/templates/beauty_salon/thumbnail.jpg",
        sections=[
            {"type": "hero", "name": "Hero Section", "required": True},
            {"type": "services", "name": "Services Grid", "required": True},
            {"type": "gallery", "name": "Portfolio Gallery", "required": True},
            {"type": "offers", "name": "Special Offers", "required": False},
            {"type": "team", "name": "Team Section", "required": False},
            {"type": "contact", "name": "Contact & Booking", "required": True},
            {"type": "footer", "name": "Footer", "required": True}
        ],
        variables=[
            {"name": "business_name", "type": "string", "required": True},
            {"name": "tagline", "type": "string", "required": False},
            {"name": "phone", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": True},
            {"name": "address", "type": "string", "required": True},
            {"name": "social_links", "type": "object", "required": False}
        ]
    )
]

for tpl in DEFAULT_TEMPLATES:
    templates_db[tpl.id] = tpl


# ========== Website Endpoints ==========

@router.post("", response_model=Website, status_code=201)
async def create_website(website: WebsiteCreate) -> Website:
    """Create a new website."""
    from datetime import datetime
    
    new_website = Website(
        id=f"site-{len(websites_db) + 1:04d}",
        name=website.name,
        tenant_id=website.tenant_id,
        template_type=website.template_type,
        custom_domain=website.custom_domain,
        ssl_enabled=website.ssl_enabled,
        status=website.status,
        pages=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    websites_db[new_website.id] = new_website
    return new_website


@router.get("", response_model=List[Website])
async def list_websites(tenant_id: Optional[str] = None) -> List[Website]:
    """List all websites, optionally filtered by tenant."""
    websites = list(websites_db.values())
    if tenant_id:
        websites = [w for w in websites if w.tenant_id == tenant_id]
    return websites


@router.get("/{website_id}", response_model=Website)
async def get_website(website_id: str) -> Website:
    """Get a specific website by ID."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    return websites_db[website_id]


@router.put("/{website_id}", response_model=Website)
async def update_website(website_id: str, update: WebsiteUpdate) -> Website:
    """Update a website."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    
    website = websites_db[website_id]
    update_data = update.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        setattr(website, key, value)
    
    from datetime import datetime
    website.updated_at = datetime.utcnow()
    return website


@router.delete("/{website_id}", status_code=204)
async def delete_website(website_id: str) -> None:
    """Delete a website."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    del websites_db[website_id]


@router.post("/{website_id}/publish", response_model=Website)
async def publish_website(website_id: str) -> Website:
    """Publish a website."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    
    website = websites_db[website_id]
    from datetime import datetime
    website.status = WebsiteStatus.PUBLISHED
    website.published_at = datetime.utcnow()
    website.updated_at = datetime.utcnow()
    return website


# ========== Template Endpoints ==========

@router.get("/templates", response_model=List[Template])
async def list_templates() -> List[Template]:
    """List all available templates."""
    return list(templates_db.values())


@router.get("/templates/{template_id}", response_model=Template)
async def get_template(template_id: str) -> Template:
    """Get a specific template."""
    if template_id not in templates_db:
        raise HTTPException(status_code=404, detail="Template not found")
    return templates_db[template_id]


@router.post("/{website_id}/apply-template/{template_id}", response_model=Website)
async def apply_template(website_id: str, template_id: str) -> Website:
    """Apply a template to a website."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    if template_id not in templates_db:
        raise HTTPException(status_code=404, detail="Template not found")
    
    website = websites_db[website_id]
    template = templates_db[template_id]
    
    # Apply template sections to create default pages
    from datetime import datetime
    from uuid import uuid4
    
    home_page = Page(
        id=str(uuid4()),
        website_id=website_id,
        title="Home",
        slug="/",
        sections=[
            Section(id=str(uuid4()), type=s["type"], order=i, content={}, styles={})
            for i, s in enumerate(template.sections)
        ],
        is_home=True
    )
    
    website.pages.append(home_page)
    website.template_type = template.type
    website.updated_at = datetime.utcnow()
    
    return website


# ========== Page Endpoints ==========

@router.get("/{website_id}/pages", response_model=List[Page])
async def list_pages(website_id: str) -> List[Page]:
    """List all pages for a website."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    return websites_db[website_id].pages


@router.post("/{website_id}/pages", response_model=Page, status_code=201)
async def create_page(website_id: str, page: PageCreate) -> Page:
    """Create a new page for a website."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    
    from uuid import uuid4
    new_page = Page(
        id=str(uuid4()),
        website_id=website_id,
        title=page.title,
        slug=page.slug,
        sections=[],
        is_home=page.is_home
    )
    websites_db[website_id].pages.append(new_page)
    return new_page


@router.put("/{website_id}/pages/{page_id}", response_model=Page)
async def update_page(website_id: str, page_id: str, update: PageUpdate) -> Page:
    """Update a page."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    
    website = websites_db[website_id]
    page = next((p for p in website.pages if p.id == page_id), None)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(page, key, value)
    
    return page


# ========== Section Endpoints ==========

@router.get("/{website_id}/sections", response_model=List[Section])
async def list_sections(website_id: str, page_id: Optional[str] = None) -> List[Section]:
    """List sections for a website's pages."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    
    website = websites_db[website_id]
    if page_id:
        page = next((p for p in website.pages if p.id == page_id), None)
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        return page.sections
    
    # Return all sections from all pages
    return [s for page in website.pages for s in page.sections]


@router.put("/{website_id}/sections/{section_id}", response_model=Section)
async def update_section(website_id: str, section_id: str, section: Section) -> Section:
    """Update a section."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    
    website = websites_db[website_id]
    for page in website.pages:
        for s in page.sections:
            if s.id == section_id:
                s.content = section.content
                s.styles = section.styles
                s.order = section.order
                return s
    
    raise HTTPException(status_code=404, detail="Section not found")


# ========== Domain & SSL Endpoints ==========

@router.post("/{website_id}/domain", response_model=DomainConfig)
async def configure_domain(website_id: str, domain: str) -> DomainConfig:
    """Configure custom domain for a website."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    
    config = DomainConfig(domain=domain, ssl_status="pending")
    return config


@router.post("/{website_id}/ssl", response_model=DomainConfig)
async def provision_ssl(website_id: str) -> DomainConfig:
    """Provision SSL certificate for a website."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    
    website = websites_db[website_id]
    config = DomainConfig(
        domain=website.custom_domain or "",
        ssl_status="provisioning"
    )
    return config


# ========== Booking Widget Endpoints ==========

@router.get("/{website_id}/booking-widget", response_model=BookingWidgetConfig)
async def get_booking_widget(website_id: str) -> BookingWidgetConfig:
    """Get booking widget configuration."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    
    return BookingWidgetConfig(enabled=True)


@router.put("/{website_id}/booking-widget", response_model=BookingWidgetConfig)
async def update_booking_widget(website_id: str, config: BookingWidgetConfig) -> BookingWidgetConfig:
    """Update booking widget configuration."""
    if website_id not in websites_db:
        raise HTTPException(status_code=404, detail="Website not found")
    
    return config