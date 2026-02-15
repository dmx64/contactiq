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
