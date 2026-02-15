#!/bin/bash
# ContactIQ — Push to GitHub
# Run this script in the folder with downloaded files

set -e

# Init repo
git init
git branch -m main
git add -A
git commit -m "Initial commit: ContactIQ backend with 11 real data providers

- Flask API server with SQLite (server.py)
- 11 free data providers: GitHub, Wikidata, Gravatar, Mailcheck,
  Clearbit Logo, OpenCorporates, SEC EDGAR, OpenSanctions,
  Google News RSS, GNews, Guardian (providers.py)
- Full test suite: 59 API tests + provider integration tests
- AI agent tool interface (OpenAI/Claude/MCP compatible)
- Dual auth: JWT + API keys
- News monitoring with auto-classification & sentiment analysis
- Sanctions/PEP screening via OpenSanctions"

# Push
git remote add origin https://github.com/dmx64/contactiq.git
git push -u origin main

echo ""
echo "✓ Pushed to https://github.com/dmx64/contactiq"
