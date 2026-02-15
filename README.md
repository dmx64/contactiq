# ContactIQ

AI-powered contact intelligence platform. Enriches contacts from 11 free public APIs, monitors news in real-time, screens against sanctions lists, and exposes a universal tool interface for AI agents (OpenAI / Claude / MCP).

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
python3 server.py
```

Server starts at `http://localhost:5000`. API docs at `/api/v1/agent/tools`.

## API Overview

| Module | Endpoints | Description |
|---|---|---|
| Auth | `/auth/register`, `/auth/login`, `/auth/api-key` | JWT + API key dual auth |
| Contacts | `/contacts` (CRUD), `/contacts/import` | Create, search, bulk import |
| Enrichment | `/enrichment/enrich`, `/enrichment/providers` | Multi-provider enrichment |
| Monitoring | `/monitoring/scan`, `/monitoring/stats` | News scanning & alerts |
| Alerts | `/alerts`, `/alerts/summary` | Filter, read, dismiss alerts |
| Agent Tools | `/agent/tool`, `/agent/tools` | Universal AI tool dispatcher |

## Data Providers (11 integrated)

All providers work with **$0/month** budget. Mock fallback when offline.

| Provider | Type | Limit | Data |
|---|---|---|---|
| GitHub API | Person | 5,000/hr | Profile, company, repos, skills |
| Wikidata | Person | ∞ | Bio, occupation, education, nationality |
| Gravatar | Person | ∞ | Avatar, display name |
| Mailcheck.ai | Identity | ∞ | Email validation, disposable check |
| Clearbit Logo | Company | ∞ | Company logos by domain |
| OpenCorporates | Company | Free/research | Directors, registrations, 170+ countries |
| SEC EDGAR | Company | 10/sec | US public company filings & officers |
| OpenSanctions | Compliance | Free bulk | Sanctions, PEP screening |
| Google News RSS | News | ∞ | Unlimited news monitoring |
| GNews API | News | 100/day | 60K+ sources (needs free key) |
| Guardian API | News | 5,000/day | Full article text (needs free key) |

## AI Agent Integration

```bash
# Get tool definitions
curl http://localhost:5000/api/v1/agent/tools?format=openai \
  -H "X-API-Key: ciq_..."

# Execute any tool
curl -X POST http://localhost:5000/api/v1/agent/tool \
  -H "X-API-Key: ciq_..." \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "search_contacts", "arguments": {"query": "CEO"}}'
```

Available tools: `search_contacts`, `get_contact`, `enrich_contact`, `get_alerts`, `monitor_contact`, `add_contact`, `contact_report`.

## Tests

```bash
# Start server in background
python3 server.py &

# Run API tests (59 tests)
python3 test_api.py

# Run provider tests (11 providers)
python3 test_providers.py
```

## Project Structure

```
├── server.py           # Flask API server (1,474 lines)
├── providers.py        # 11 real data providers (1,088 lines)
├── test_api.py         # Full API test suite (59 tests)
├── test_providers.py   # Provider integration tests
├── requirements.txt
├── .env.example
└── .gitignore
```

## License

MIT

## OSINT Intelligence (NEW!)

Deep contact investigation using 5 specialized OSINT tools.

### OSINT Providers

| Tool | Purpose | Coverage | Speed |
|------|---------|----------|-------|
| **Sherlock** | Username → Social profiles | 300+ platforms | ~2 min |
| **theHarvester** | Email → Related data | Multiple sources | ~1 min |
| **holehe** | Email → Platform registrations | 120+ platforms | ~30 sec |
| **subfinder** | Domain → Subdomains | Passive enum | ~30 sec |
| **phoneinfoga** | Phone → Carrier/validation | Phone intelligence | ~30 sec |

### OSINT Endpoints

```bash
# Email OSINT - Find related emails, platform registrations
curl -X POST http://localhost:5000/api/v1/osint/email \
  -H "X-API-Key: ciq_..." \
  -d '{"email": "target@example.com"}'

# Username search across 300+ social platforms
curl -X POST http://localhost:5000/api/v1/osint/username \
  -H "X-API-Key: ciq_..." \
  -d '{"username": "johndoe"}'

# Phone number intelligence
curl -X POST http://localhost:5000/api/v1/osint/phone \
  -H "X-API-Key: ciq_..." \
  -d '{"phone": "+1234567890"}'

# Domain OSINT - WHOIS, DNS, subdomains
curl -X POST http://localhost:5000/api/v1/osint/domain \
  -H "X-API-Key: ciq_..." \
  -d '{"domain": "example.com"}'
```

### AI OSINT Tools

```bash
# Get OSINT tools
curl http://localhost:5000/api/v1/agent/tools?format=openai \
  -H "X-API-Key: ciq_..."

# Execute OSINT tool
curl -X POST http://localhost:5000/api/v1/agent/tool \
  -H "X-API-Key: ciq_..." \
  -d '{
    "tool_name": "osint_email",
    "arguments": {"email": "target@example.com"}
  }'
```

**Available OSINT tools:**
- `osint_email` - Deep email investigation
- `osint_username` - Social profile search
- `osint_phone` - Phone validation & carrier
- `osint_domain` - Domain & subdomain intel

### OSINT CLI

Direct OSINT from command line:

```bash
# Email OSINT
./osint_contact.py email john@example.com

# Username search
./osint_contact.py username johndoe

# Phone OSINT
./osint_contact.py phone +1234567890

# Domain OSINT
./osint_contact.py domain example.com
```

Results saved to `/tmp/osint_<type>_<value>.json`

### Combined Intelligence

Use both standard providers + OSINT for maximum intel:

```python
# 1. Standard enrichment (GitHub, Wikidata, Gravatar, etc.)
POST /api/v1/enrichment/enrich
{
  "contact_id": "123",
  "providers": ["github", "wikidata", "gravatar"]
}

# 2. OSINT deep dive
POST /api/v1/osint/email
{"email": "contact@example.com"}

POST /api/v1/osint/username
{"username": "contact_username"}

# Result: Comprehensive 360° profile
```

### Legal & Ethical OSINT

**CRITICAL:** OSINT must be conducted legally and ethically.

**Legal:**
✅ Public information only  
✅ No authentication bypass  
✅ Respect Terms of Service  
✅ No unauthorized access  

**Illegal:**
❌ Hacking or password cracking  
❌ Bypassing security  
❌ Harassment or stalking  
❌ Violating platform ToS  

See `references/legal.md` for full guidelines.

### Total Data Sources

**Standard Providers:** 11
- GitHub, Wikidata, Gravatar, Mailcheck, Clearbit Logo
- OpenCorporates, SEC EDGAR, OpenSanctions
- Google News, GNews, Guardian

**OSINT Tools:** 5
- Sherlock, theHarvester, holehe, subfinder, phoneinfoga

**Total:** 16 intelligence sources

