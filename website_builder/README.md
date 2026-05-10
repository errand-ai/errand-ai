# Website Builder MVP Implementation

This directory contains the implementation for the white-label website builder MVP for Errand AI.

## Architecture Overview

```
website_builder/
├── backend/              # FastAPI backend for website management
│   ├── routes/          # API endpoints
│   ├── services/        # Business logic
│   └── models/         # Database models
├── frontend/            # Vue 3 frontend
│   ├── components/     # UI components
│   │   ├── page-builder/   # Page builder components
│   │   ├── templates/      # Template components
│   │   └── booking/        # Booking widget
│   └── pages/          # Vue pages
├── templates/          # Pre-built website templates
│   ├── hairdresser/    # Hairdresser template
│   ├── massage/       # Massage template
│   └── beauty_salon/  # Beauty salon template
├── deployments/        # Deployment configurations
│   ├── docker/        # Docker compose files
│   └── k8s/          # Kubernetes manifests
└── docs/             # Documentation
```

## MVP Features

### Core MVP (Implemented)
1. **3 Initial Templates**: Hairdresser, Massage, Beauty Salon
2. **Basic Page Builder**: Pre-built sections that can be reordered
3. **Booking Widget Integration**: Embeddable booking widget
4. **Custom Domain Support**: SSL provisioning
5. **Tenant Admin Panel**: Website management interface

### Future Releases (Not MVP)
- Full drag-and-drop page builder
- Blog/news section
- Advanced SEO tools
- Image CDN integration
- E-commerce features

## API Endpoints

### Website Management
- `POST /api/websites` - Create new website
- `GET /api/websites/{id}` - Get website details
- `PUT /api/websites/{id}` - Update website
- `DELETE /api/websites/{id}` - Delete website
- `POST /api/websites/{id}/publish` - Publish website

### Template Management
- `GET /api/templates` - List available templates
- `GET /api/templates/{id}` - Get template details
- `POST /api/websites/{id}/apply-template/{template_id}` - Apply template

### Page Builder
- `GET /api/websites/{id}/pages` - List pages
- `POST /api/websites/{id}/pages` - Create page
- `PUT /api/websites/{id}/pages/{page_id}` - Update page
- `GET /api/websites/{id}/sections` - Get page sections
- `PUT /api/websites/{id}/sections/{section_id}` - Update section

### Domain Management
- `POST /api/websites/{id}/domain` - Configure custom domain
- `POST /api/websites/{id}/ssl` - Provision SSL certificate

## Dependencies

- ERR-25: Website Builder PRD
- ERR-26: Website Builder Technical Specification
- ERR-22: Booking System Technical Specification

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Using Docker
docker-compose up -d
```

## License

Proprietary - Errand AI