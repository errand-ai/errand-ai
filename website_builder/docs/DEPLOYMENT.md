# Website Builder MVP - Deployment Guide

## Overview

The Website Builder MVP enables Errand AI tenants to create and manage white-label websites for their businesses. The system provides:
- 3 pre-built templates (hairdresser, massage, beauty salon)
- Basic page builder with pre-built sections
- Booking widget integration
- Custom domain support with SSL
- Multi-tenant architecture

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Tenant Website                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Frontend   │  │   Booking   │  │   Static Assets     │ │
│  │  (Tailwind) │  │   Widget    │  │   (Images, Fonts)   │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Website Builder API                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Websites  │  │  Templates  │  │   Page Builder      │ │
│  │   Routes    │  │   Manager   │  │   Engine           │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Infrastructure                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  PostgreSQL │  │    Redis    │  │   CDN/Edge         │ │
│  │   (Data)    │  │  (Cache)    │  │   (CloudFront)     │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Deployment Options

### Option 1: Docker Compose (Development)

```bash
cd website_builder/deployments/docker
docker-compose up -d
```

The API will be available at `http://localhost:8001`

### Option 2: Kubernetes (Production)

```bash
cd website_builder/deployments/k8s
kubectl apply -f .
```

## API Endpoints

### Website Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/websites` | Create new website |
| GET | `/api/websites` | List all websites |
| GET | `/api/websites/{id}` | Get website details |
| PUT | `/api/websites/{id}` | Update website |
| DELETE | `/api/websites/{id}` | Delete website |
| POST | `/api/websites/{id}/publish` | Publish website |

### Templates

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/websites/templates` | List available templates |
| GET | `/api/websites/templates/{id}` | Get template details |
| POST | `/api/websites/{id}/apply-template/{template_id}` | Apply template |

### Pages & Sections

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/websites/{id}/pages` | List pages |
| POST | `/api/websites/{id}/pages` | Create page |
| PUT | `/api/websites/{id}/pages/{page_id}` | Update page |
| GET | `/api/websites/{id}/sections` | List sections |
| PUT | `/api/websites/{id}/sections/{section_id}` | Update section |

### Domain & SSL

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/websites/{id}/domain` | Configure domain |
| POST | `/api/websites/{id}/ssl` | Provision SSL |

### Booking Widget

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/websites/{id}/booking-widget` | Get widget config |
| PUT | `/api/websites/{id}/booking-widget` | Update widget config |

## Template Variables

Templates support the following variables:

| Variable | Type | Description |
|----------|------|-------------|
| `business_name` | string | Business name |
| `tagline` | string | Tagline/motto |
| `phone` | string | Contact phone |
| `email` | string | Contact email |
| `address` | string | Physical address |
| `social_links` | object | Social media links |
| `opening_hours` | object | Business hours |

## Section Types

| Type | Description |
|------|-------------|
| `hero` | Hero/banner section |
| `services` | Services grid |
| `gallery` | Image gallery |
| `testimonials` | Client reviews |
| `contact` | Contact form/info |
| `about` | About section |
| `pricing` | Pricing table |
| `team` | Team/staff section |
| `footer` | Footer section |
| `offers` | Special offers |

## Custom Domain Setup

1. Configure your domain in the tenant admin panel
2. Add CNAME record pointing to your deployment
3. Call the SSL provisioning endpoint
4. SSL certificates are automatically managed via Let's Encrypt

## Booking Widget Integration

The booking widget can be embedded on any website:

```html
<script src="https://your-domain.com/embed/booking-widget.js" defer></script>
<script>
  // Initialize with website ID
  BookingWidget.init({
    websiteId: 'site-0001',
    position: 'bottom-right', // or 'bottom-left', 'inline'
    theme: 'light', // or 'dark'
    primaryColor: '#1E40AF'
  });
</script>
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
| `REDIS_URL` | No | - | Redis connection string |
| `JWT_SECRET` | Yes | - | JWT signing secret |
| `CORS_ORIGINS` | No | `*` | Allowed CORS origins |

## Monitoring

- Health check: `GET /health`
- API documentation: `GET /docs` (Swagger UI)

## Future Enhancements

- Full drag-and-drop page builder
- Blog/news section
- Advanced SEO tools
- Image CDN integration
- E-commerce features