# ContactIQ

**Comprehensive Contact Intelligence Platform** - Mobile app with self-hosted backend that combines 17 data sources for contact enrichment, caller ID, OSINT investigations, and digital business cards.

## 🚀 Quick Start

### Backend Setup
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
python server.py
```
Server starts at `http://localhost:5000`

### Mobile App Setup  
```bash
cd mobile
npm install
npx expo start
```

## 📱 Mobile Application

React Native app with **6 core screens** and **2,058 lines of code**:

- **Dashboard** - Overview and quick actions
- **Contacts** - Contact management and enrichment
- **Caller ID** - Real-time caller identification with spam detection
- **OSINT** - Deep investigation tools across 5 specialized platforms
- **QR Card** - Digital business card generator and scanner
- **Settings** - Profile and app configuration

### Tech Stack
- **Frontend**: React Native + Expo
- **State Management**: Zustand
- **Authentication**: Expo SecureStore + JWT
- **UI Theme**: Dark intelligence-themed interface
- **Navigation**: React Navigation v6

## 🔧 Backend Architecture

Flask API server with **56 endpoints** across 7 modules:

| Module | Endpoints | Description |
|--------|-----------|-------------|
| **Auth** | 8 endpoints | JWT + API key authentication |
| **Contacts** | 12 endpoints | CRUD, search, bulk import, enrichment |
| **Caller ID** | 6 endpoints | Real-time identification, spam detection |
| **OSINT** | 10 endpoints | Deep investigation across 5 tools |
| **QR Cards** | 8 endpoints | Digital business card management |
| **Monitoring** | 7 endpoints | News scanning, alerts, sanctions |
| **Agent Tools** | 5 endpoints | AI agent integration (OpenAI/Claude) |

## 📊 Data Sources (17 Total)

### API Providers (12)
| Provider | Type | Rate Limit | Data Coverage |
|----------|------|------------|---------------|
| GitHub API | Person | 5,000/hr | Profiles, repos, skills |
| Wikidata | Person | ∞ | Bio, occupation, nationality |
| Gravatar | Person | ∞ | Avatars, display names |
| Mailcheck.ai | Email | ∞ | Validation, disposable detection |
| Clearbit Logo | Company | ∞ | Company logos by domain |
| OpenCorporates | Company | Free tier | 170+ countries, directors |
| SEC EDGAR | Company | 10/sec | US public filings, officers |
| OpenSanctions | Compliance | Free | PEP, sanctions screening |
| Google News | News | ∞ | Real-time monitoring |
| GNews API | News | 100/day | 60K+ sources |
| Guardian API | News | 5,000/day | Full article text |
| Hunter.io | Email | 25/mo free | Email finder and verification |

### OSINT CLI Tools (5)
| Tool | Purpose | Coverage | Speed |
|------|---------|----------|-------|
| **Sherlock** | Username → Social profiles | 300+ platforms | ~2 min |
| **theHarvester** | Email → Related intelligence | Multiple sources | ~1 min |
| **holehe** | Email → Platform registrations | 120+ services | ~30 sec |
| **subfinder** | Domain → Subdomains | Passive enumeration | ~30 sec |
| **phoneinfoga** | Phone → Carrier validation | Global coverage | ~30 sec |

## 🎯 Target Markets

### Primary Users
- **Sales Professionals** - Lead enrichment and verification
- **Recruiters** - Candidate research and contact discovery  
- **Journalists** - Source verification and background checks
- **Private Investigators** - Subject research and asset tracing
- **OSINT Analysts** - Intelligence gathering and verification

### Business Model
- **Free Tier**: Basic contact enrichment (5 API sources)
- **Pro ($4.99/mo)**: Full API access + basic OSINT tools
- **Enterprise ($29.99/mo)**: Complete platform + priority support

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  React Native   │────│   Flask API      │────│   Data Sources  │
│  Mobile App     │    │   (56 endpoints) │    │   (17 providers) │
│                 │    │                  │    │                 │
│ • 6 Screens     │    │ • Authentication │    │ • 12 APIs       │
│ • Zustand Store│    │ • Contact Mgmt   │    │ • 5 OSINT Tools │
│ • Expo Runtime │    │ • OSINT Engine   │    │ • Real-time     │
│ • Dark UI       │    │ • Caller ID      │    │ • Privacy-first │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🔒 Privacy & Security

- **Self-hosted architecture** - Full data control
- **No third-party tracking** - Privacy-first design
- **Encrypted storage** - SecureStore for sensitive data
- **API rate limiting** - Abuse prevention
- **Audit logging** - Complete activity tracking

## 📈 Project Status

### Completed ✅
- [x] Backend API with 56 endpoints
- [x] React Native mobile app (6 screens)
- [x] 17 data source integrations
- [x] Authentication system (JWT + API keys)
- [x] OSINT investigation tools
- [x] Caller ID with spam detection
- [x] Digital QR business cards
- [x] Real-time news monitoring
- [x] Comprehensive test suite
- [x] Documentation and investor brief

### Roadmap 🚀
- [ ] iOS/Android app store deployment
- [ ] Advanced analytics dashboard
- [ ] Team collaboration features
- [ ] API marketplace for third-party integrations
- [ ] AI-powered contact scoring
- [ ] Blockchain identity verification

## 🚀 Deployment

### Development
```bash
# Backend
cd backend && python server.py

# Mobile (separate terminal)
cd mobile && npx expo start
```

### Production
```bash
# Deploy to your server
chmod +x scripts/deploy.sh
./scripts/deploy.sh your-server-ip
```

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed instructions.

## 🧪 Testing

```bash
# Backend API tests (59 tests)
cd backend && python test_api.py

# Provider integration tests
python test_providers.py

# Mobile app testing
cd mobile && npm test
```

## 📚 Documentation

- [API Documentation](docs/API.md) - Complete endpoint reference
- [Investor Brief](docs/INVESTOR-BRIEF.md) - Business overview and projections
- [Deployment Guide](docs/DEPLOYMENT.md) - Production setup instructions

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

## 🏢 Business Contact

**ContactIQ** - Comprehensive Contact Intelligence Platform
- **Revenue Model**: Freemium (Free → Pro $4.99/mo → Enterprise $29.99/mo)
- **Market Size**: $8.2B contact intelligence market
- **Funding Stage**: Pre-seed ($150K-$300K target)
- **Competitive Edge**: Only mobile-first, self-hosted solution combining contact enrichment + OSINT + caller ID

---

**Built with ❤️ for privacy-conscious professionals who need comprehensive contact intelligence.**
