# ContactIQ API Documentation

Complete reference for all 56 API endpoints across 7 modules.

## Base URL
```
Production: https://your-server.com/api/v1
Development: http://localhost:5000/api/v1
```

## Authentication
All endpoints require either:
- **JWT Token**: `Authorization: Bearer <token>`
- **API Key**: `X-API-Key: ciq_...`

## Rate Limiting
- **Free tier**: 100 requests/hour
- **Pro tier**: 1,000 requests/hour  
- **Enterprise**: Unlimited

---

## 📱 Authentication Module (8 endpoints)

### POST `/auth/register`
Register new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "secure_password"
}
```

**Response:**
```json
{
  "user_id": 123,
  "email": "user@example.com",
  "api_key": "ciq_abc123...",
  "access_token": "eyJ0eXAi...",
  "tier": "free"
}
```

### POST `/auth/login`
User authentication.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "secure_password"
}
```

### POST `/auth/refresh`
Refresh JWT token.

**Headers:** `Authorization: Bearer <token>`

### GET `/auth/profile`
Get user profile and statistics.

**Headers:** `X-API-Key: ciq_...`

**Response:**
```json
{
  "email": "user@example.com",
  "tier": "pro",
  "created_at": "2024-01-01T00:00:00Z",
  "stats": {
    "total_contacts": 245,
    "caller_queries": 89,
    "osint_queries": 34
  }
}
```

### PUT `/auth/change-password`
Change user password.

### PUT `/auth/regenerate-api-key`
Generate new API key (invalidates old one).

### PUT `/auth/upgrade-tier`
Upgrade user subscription tier.

**Request:**
```json
{
  "tier": "pro" // "free", "pro", "enterprise"
}
```

### DELETE `/auth/delete-account`
Permanently delete user account and all data.

---

## 👥 Contacts Module (12 endpoints)

### GET `/contacts`
List all contacts with search and pagination.

**Query Parameters:**
- `page` (int): Page number (default: 1)
- `limit` (int): Results per page (max: 100)
- `search` (string): Search in name/email/company
- `sort_by` (string): Sort field (default: created_at)
- `order` (string): asc/desc (default: desc)

**Response:**
```json
{
  "contacts": [
    {
      "id": 123,
      "email": "john@example.com",
      "phone": "+1234567890",
      "name": "John Doe",
      "company": "Acme Corp",
      "source": "manual",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 245,
    "pages": 5
  }
}
```

### POST `/contacts`
Create new contact.

**Request:**
```json
{
  "email": "john@example.com",
  "phone": "+1234567890",
  "name": "John Doe",
  "company": "Acme Corp"
}
```

### GET `/contacts/{id}`
Get single contact with enriched data.

**Response:**
```json
{
  "id": 123,
  "email": "john@example.com",
  "name": "John Doe",
  "enriched_data": {
    "github": {
      "login": "johndoe",
      "company": "Acme Corp",
      "public_repos": 42
    },
    "gravatar": {
      "avatar_url": "https://...",
      "display_name": "John Doe"
    }
  }
}
```

### PUT `/contacts/{id}`
Update contact information.

### DELETE `/contacts/{id}`
Delete contact.

### POST `/contacts/import`
Bulk import contacts from CSV/JSON.

### POST `/contacts/{id}/enrich`
Enrich single contact with data providers.

**Request:**
```json
{
  "providers": ["github", "gravatar", "wikidata"],
  "force_refresh": false
}
```

### GET `/contacts/{id}/enrichment-history`
Get enrichment history for contact.

### POST `/contacts/bulk-enrich`
Enrich multiple contacts at once.

### GET `/contacts/export`
Export contacts to CSV/JSON.

### POST `/contacts/{id}/merge`
Merge duplicate contacts.

### GET `/contacts/stats`
Get contact statistics and insights.

---

## 📞 Caller ID Module (6 endpoints)

### POST `/caller-id/identify`
Identify incoming phone number.

**Request:**
```json
{
  "phone": "+1234567890",
  "country_code": "US"
}
```

**Response:**
```json
{
  "phone": "+1234567890",
  "name": "John Doe",
  "company": "Acme Corp",
  "carrier": "Verizon",
  "location": "New York, NY",
  "spam_score": 0.15,
  "confidence": 0.95,
  "sources": ["truecaller", "whitepages"]
}
```

### GET `/caller-id/history`
Get caller ID query history.

### POST `/caller-id/report-spam`
Report number as spam.

**Request:**
```json
{
  "phone": "+1234567890",
  "reason": "robocall",
  "details": "Automated sales call"
}
```

### GET `/caller-id/blocked`
Get blocked numbers list.

### POST `/caller-id/block`
Add number to block list.

### DELETE `/caller-id/block/{phone}`
Remove number from block list.

---

## 🔍 OSINT Module (10 endpoints)

### POST `/osint/email`
Deep email investigation.

**Request:**
```json
{
  "email": "target@example.com",
  "tools": ["theharvester", "holehe"],
  "timeout": 120
}
```

**Response:**
```json
{
  "investigation_id": "osint_abc123",
  "email": "target@example.com",
  "status": "completed",
  "results": {
    "theharvester": {
      "emails": ["target@example.com", "alt@example.com"],
      "domains": ["example.com"],
      "execution_time": 45
    },
    "holehe": {
      "registered_sites": ["twitter", "github", "linkedin"],
      "total_sites": 3,
      "execution_time": 12
    }
  }
}
```

### POST `/osint/username`
Search username across 300+ social platforms.

**Request:**
```json
{
  "username": "johndoe",
  "platforms": "all" // or ["twitter", "github", "instagram"]
}
```

### POST `/osint/phone`
Phone number intelligence.

**Request:**
```json
{
  "phone": "+1234567890"
}
```

### POST `/osint/domain`
Domain and subdomain reconnaissance.

**Request:**
```json
{
  "domain": "example.com",
  "include_subdomains": true
}
```

### GET `/osint/investigations`
List OSINT investigation history.

### GET `/osint/investigations/{id}`
Get investigation details and results.

### DELETE `/osint/investigations/{id}`
Delete investigation record.

### GET `/osint/tools`
List available OSINT tools and status.

**Response:**
```json
{
  "tools": {
    "sherlock": {
      "enabled": true,
      "platforms": 300,
      "avg_time": 120
    },
    "theharvester": {
      "enabled": true,
      "sources": 12,
      "avg_time": 60
    }
  }
}
```

### POST `/osint/tools/{tool}/toggle`
Enable/disable specific OSINT tool.

### POST `/osint/batch`
Run batch OSINT investigation on multiple targets.

---

## 📱 QR Cards Module (8 endpoints)

### GET `/qr-cards/personal`
Get user's personal QR business card.

### POST `/qr-cards/personal`
Create/update personal QR card.

**Request:**
```json
{
  "name": "John Doe",
  "title": "Software Engineer",
  "company": "Acme Corp",
  "email": "john@example.com",
  "phone": "+1234567890",
  "website": "https://johndoe.com"
}
```

### GET `/qr-cards/saved`
List saved QR cards from other contacts.

### POST `/qr-cards/scan`
Process scanned QR card data.

**Request:**
```json
{
  "qr_data": "BEGIN:VCARD\nVERSION:3.0\nFN:John Doe\n..."
}
```

### GET `/qr-cards/history`
Get QR code scan history.

### POST `/qr-cards/save`
Save QR card to contacts.

### GET `/qr-cards/{id}/export`
Export QR card as image/PDF.

### DELETE `/qr-cards/{id}`
Delete saved QR card.

---

## 🚨 Monitoring & Alerts Module (7 endpoints)

### GET `/alerts`
Get user alerts with filtering.

**Query Parameters:**
- `type`: Alert type filter
- `severity`: Severity filter (low/medium/high)
- `unread_only`: Boolean

### POST `/alerts`
Create custom alert.

### PUT `/alerts/{id}/read`
Mark alert as read.

### DELETE `/alerts/{id}`
Delete alert.

### POST `/monitoring/scan`
Start monitoring scan for contact.

**Request:**
```json
{
  "contact_id": 123,
  "monitor_types": ["news", "sanctions", "social"],
  "frequency": "daily"
}
```

### GET `/monitoring/stats`
Get monitoring statistics.

### POST `/monitoring/stop/{contact_id}`
Stop monitoring for contact.

---

## 🤖 AI Agent Tools Module (5 endpoints)

### GET `/agent/tools`
Get AI tool definitions.

**Query Parameters:**
- `format`: "openai" or "claude" or "mcp"

**Response (OpenAI format):**
```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_contacts",
        "description": "Search contacts in database",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10}
          }
        }
      }
    }
  ]
}
```

### POST `/agent/tool`
Execute AI agent tool.

**Request:**
```json
{
  "tool_name": "search_contacts",
  "arguments": {
    "query": "CEO",
    "limit": 5
  }
}
```

### GET `/agent/capabilities`
Get platform capabilities for AI agents.

### POST `/agent/batch-tools`
Execute multiple tools in sequence.

### GET `/agent/usage`
Get AI agent usage statistics.

---

## Error Responses

All endpoints return standard HTTP status codes:

- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `409` - Conflict
- `429` - Rate Limited
- `500` - Server Error

**Error Format:**
```json
{
  "error": "Invalid API key",
  "code": "AUTH_INVALID_KEY",
  "details": "The provided API key is not valid or has been revoked"
}
```

---

## Rate Limiting Headers

All responses include rate limit headers:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1640995200
```

---

## Webhooks (Optional)

Configure webhooks for real-time notifications:

### Events
- `contact.created`
- `contact.enriched`
- `osint.completed`
- `alert.triggered`
- `caller.identified`

### Webhook Payload
```json
{
  "event": "contact.enriched",
  "data": {
    "contact_id": 123,
    "enrichment_sources": ["github", "gravatar"]
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

## SDK Examples

### JavaScript/Node.js
```javascript
const ContactIQ = require('contactiq-sdk');

const client = new ContactIQ({
  apiKey: 'ciq_your_api_key',
  baseURL: 'https://your-server.com/api/v1'
});

// Search contacts
const contacts = await client.contacts.search('john@example.com');

// OSINT investigation  
const osint = await client.osint.email('target@example.com');
```

### Python
```python
from contactiq import ContactIQClient

client = ContactIQClient(
    api_key='ciq_your_api_key',
    base_url='https://your-server.com/api/v1'
)

# Caller ID lookup
result = client.caller_id.identify('+1234567890')

# Create QR card
qr_card = client.qr_cards.create_personal({
    'name': 'John Doe',
    'email': 'john@example.com'
})
```

---

**Total: 56 endpoints across 7 modules**
- Authentication: 8 endpoints
- Contacts: 12 endpoints  
- Caller ID: 6 endpoints
- OSINT: 10 endpoints
- QR Cards: 8 endpoints
- Monitoring/Alerts: 7 endpoints
- AI Agent Tools: 5 endpoints
