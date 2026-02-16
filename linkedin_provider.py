"""
ContactIQ LinkedIn Provider
12th data provider — LinkedIn profile enrichment via linkedin-api (Voyager).

Architecture:
  Free tier  → linkedin-api (self-hosted, cookie auth, 100 req/hr)
  Pro tier   → ScrapIn API ($, real-time, no account needed)
  Enterprise → Unipile API ($$$, messaging + Sales Navigator)

Data returned:
  - Full name, headline, title, company
  - Work history (all positions)
  - Education history
  - Skills with endorsement counts
  - Profile photo URL
  - Location, industry
  - Contact info (email, phone, websites)
  - Connection count
  - Summary/about text

Integration:
  1. Add to providers.py PROVIDERS dict
  2. Register blueprint in server.py
  3. Add 'linkedin-api' to requirements.txt
"""

import os
import re
import json
import time
import logging
import hashlib
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from threading import Lock

logger = logging.getLogger('contactiq.linkedin')

# ═══════════════════════════════════════════════════════════════
# LINKEDIN CLIENT WRAPPER
# ═══════════════════════════════════════════════════════════════

class LinkedInClient:
    """
    Wrapper around linkedin-api with caching, rate limiting, and fallback.
    Thread-safe singleton pattern.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._api = None
        self._authenticated = False
        self._request_count = 0
        self._window_start = time.time()
        self._cache = {}  # In-memory cache, Redis in production

        # Config
        self.email = os.environ.get('LINKEDIN_EMAIL', '')
        self.password = os.environ.get('LINKEDIN_PASSWORD', '')
        self.scrapin_key = os.environ.get('SCRAPIN_API_KEY', '')
        self.max_requests_per_hour = int(os.environ.get('LINKEDIN_RATE_LIMIT', '80'))
        self.cache_ttl = int(os.environ.get('LINKEDIN_CACHE_TTL', '604800'))  # 7 days
        self.request_delay = float(os.environ.get('LINKEDIN_DELAY', '3.0'))  # seconds

        self._last_request_time = 0

    def _authenticate(self):
        """Authenticate with LinkedIn using cookie-based auth."""
        if self._authenticated and self._api:
            return True

        if not self.email or not self.password:
            logger.warning('LINKEDIN_EMAIL/LINKEDIN_PASSWORD not set. LinkedIn provider disabled.')
            return False

        try:
            from linkedin_api import Linkedin
            self._api = Linkedin(self.email, self.password)
            self._authenticated = True
            logger.info('LinkedIn authenticated successfully')
            return True
        except Exception as e:
            logger.error(f'LinkedIn auth failed: {e}')
            self._authenticated = False
            return False

    def _check_rate_limit(self):
        """Check if we're within rate limits. Returns True if allowed."""
        now = time.time()

        # Reset window every hour
        if now - self._window_start > 3600:
            self._request_count = 0
            self._window_start = now

        if self._request_count >= self.max_requests_per_hour:
            return False

        # Enforce minimum delay between requests
        elapsed = now - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)

        self._request_count += 1
        self._last_request_time = time.time()
        return True

    def _cache_key(self, method, *args):
        raw = f"{method}:{':'.join(str(a) for a in args)}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _get_cached(self, key):
        entry = self._cache.get(key)
        if entry and time.time() - entry['ts'] < self.cache_ttl:
            return entry['data']
        return None

    def _set_cached(self, key, data):
        self._cache[key] = {'data': data, 'ts': time.time()}

    # ─── Public API Methods ───────────────────────────────────

    def get_profile(self, public_id=None, urn_id=None):
        """
        Get full LinkedIn profile.
        public_id: LinkedIn vanity URL slug (e.g. 'billy-g')
        """
        cache_key = self._cache_key('profile', public_id or urn_id)
        cached = self._get_cached(cache_key)
        if cached:
            return {**cached, '_cached': True}

        # Try self-hosted first
        if self._authenticate() and self._check_rate_limit():
            try:
                profile = self._api.get_profile(public_id=public_id, urn_id=urn_id)
                result = self._normalize_profile(profile)

                # Also get contact info
                try:
                    contact = self._api.get_profile_contact_info(public_id=public_id, urn_id=urn_id)
                    result['contact_info'] = self._normalize_contact_info(contact)
                except Exception:
                    result['contact_info'] = {}

                # Get skills
                try:
                    skills = self._api.get_profile_skills(public_id=public_id, urn_id=urn_id)
                    result['skills'] = self._normalize_skills(skills)
                except Exception:
                    result['skills'] = []

                result['_source'] = 'linkedin-api'
                self._set_cached(cache_key, result)
                return result

            except Exception as e:
                logger.warning(f'LinkedIn API error: {e}')

        # Fallback to ScrapIn API
        if self.scrapin_key:
            return self._scrapin_fallback(public_id)

        return {'error': 'LinkedIn unavailable', '_source': 'none'}

    def search_people(self, keywords=None, current_company=None,
                      title=None, location=None, limit=10):
        """Search LinkedIn profiles."""
        cache_key = self._cache_key('search', keywords, current_company, title, location, limit)
        cached = self._get_cached(cache_key)
        if cached:
            return {**cached, '_cached': True}

        if self._authenticate() and self._check_rate_limit():
            try:
                kwargs = {}
                if keywords:
                    kwargs['keywords'] = keywords
                if current_company:
                    kwargs['current_company'] = current_company
                if title:
                    kwargs['keyword_title'] = title
                if location:
                    kwargs['regions'] = location if isinstance(location, list) else [location]

                results = self._api.search_people(**kwargs, limit=limit)
                normalized = [self._normalize_search_result(r) for r in results]

                output = {
                    'results': normalized,
                    'count': len(normalized),
                    'query': {'keywords': keywords, 'title': title, 'company': current_company},
                    '_source': 'linkedin-api',
                }
                self._set_cached(cache_key, output)
                return output

            except Exception as e:
                logger.warning(f'LinkedIn search error: {e}')

        return {'results': [], 'count': 0, 'error': str(e) if 'e' in dir() else 'unavailable'}

    def get_company(self, public_id):
        """Get LinkedIn company profile."""
        cache_key = self._cache_key('company', public_id)
        cached = self._get_cached(cache_key)
        if cached:
            return {**cached, '_cached': True}

        if self._authenticate() and self._check_rate_limit():
            try:
                company = self._api.get_company(public_id)
                result = self._normalize_company(company)
                result['_source'] = 'linkedin-api'
                self._set_cached(cache_key, result)
                return result
            except Exception as e:
                logger.warning(f'LinkedIn company error: {e}')

        return {'error': 'LinkedIn unavailable'}

    def get_connections(self, urn_id, max_connections=50):
        """Get 1st degree connections of a profile."""
        if self._authenticate() and self._check_rate_limit():
            try:
                conns = self._api.get_profile_connections(urn_id, max_connections=max_connections)
                return {
                    'connections': [self._normalize_search_result(c) for c in conns],
                    'count': len(conns),
                    '_source': 'linkedin-api',
                }
            except Exception as e:
                logger.warning(f'LinkedIn connections error: {e}')
        return {'connections': [], 'count': 0}

    def search_jobs(self, keywords, location=None, limit=10):
        """Search LinkedIn jobs."""
        if self._authenticate() and self._check_rate_limit():
            try:
                jobs = self._api.search_jobs(keywords, location_name=location, limit=limit)
                return {
                    'jobs': [self._normalize_job(j) for j in jobs],
                    'count': len(jobs),
                    '_source': 'linkedin-api',
                }
            except Exception as e:
                logger.warning(f'LinkedIn jobs error: {e}')
        return {'jobs': [], 'count': 0}

    # ─── ScrapIn Fallback ─────────────────────────────────────

    def _scrapin_fallback(self, public_id):
        """Fallback to ScrapIn API when self-hosted fails."""
        try:
            import requests
            url = 'https://api.scrapin.io/enrichment/profile'
            params = {
                'apikey': self.scrapin_key,
                'linkedInUrl': f'https://linkedin.com/in/{public_id}',
            }
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                result = self._normalize_scrapin_response(data)
                result['_source'] = 'scrapin-api'
                cache_key = self._cache_key('profile', public_id)
                self._set_cached(cache_key, result)
                return result
        except Exception as e:
            logger.warning(f'ScrapIn fallback error: {e}')

        return {'error': 'All LinkedIn sources unavailable', '_source': 'none'}

    # ─── Data Normalization ───────────────────────────────────

    def _normalize_profile(self, raw):
        """Normalize linkedin-api profile response to ContactIQ format."""
        return {
            'linkedin_id': raw.get('public_id', ''),
            'urn_id': raw.get('urn_id', ''),
            'first_name': raw.get('firstName', ''),
            'last_name': raw.get('lastName', ''),
            'full_name': f"{raw.get('firstName', '')} {raw.get('lastName', '')}".strip(),
            'headline': raw.get('headline', ''),
            'summary': raw.get('summary', ''),
            'industry': raw.get('industryName', ''),
            'location': raw.get('locationName', '') or raw.get('geoLocationName', ''),
            'country': raw.get('geoCountryName', ''),
            'photo_url': self._extract_photo(raw),
            'profile_url': f"https://linkedin.com/in/{raw.get('public_id', '')}",
            'connection_count': raw.get('connections', 0),
            'follower_count': raw.get('followerCount', 0),

            # Current position
            'current_title': self._extract_current_title(raw),
            'current_company': self._extract_current_company(raw),

            # History
            'experience': self._extract_experience(raw),
            'education': self._extract_education(raw),
            'certifications': self._extract_certifications(raw),
            'languages': self._extract_languages(raw),

            'enriched_at': datetime.utcnow().isoformat() + 'Z',
        }

    def _normalize_contact_info(self, raw):
        """Normalize contact info."""
        return {
            'email': raw.get('email_address', ''),
            'phone_numbers': raw.get('phone_numbers', []),
            'websites': [w.get('url', '') for w in raw.get('websites', [])],
            'twitter': raw.get('twitter', {}).get('name', ''),
            'ims': raw.get('ims', []),
        }

    def _normalize_skills(self, raw):
        """Normalize skills list."""
        if not raw:
            return []
        return [
            {
                'name': s.get('name', ''),
                'endorsements': s.get('endorsementCount', 0),
            }
            for s in raw
        ]

    def _normalize_search_result(self, raw):
        """Normalize search result."""
        return {
            'urn_id': raw.get('urn_id', ''),
            'public_id': raw.get('public_id', ''),
            'name': raw.get('name', ''),
            'headline': raw.get('jobtitle', '') or raw.get('headline', ''),
            'location': raw.get('location', ''),
            'profile_url': f"https://linkedin.com/in/{raw.get('public_id', '')}" if raw.get('public_id') else '',
        }

    def _normalize_company(self, raw):
        """Normalize company profile."""
        return {
            'name': raw.get('name', ''),
            'universal_name': raw.get('universalName', ''),
            'description': raw.get('description', ''),
            'website': raw.get('companyPageUrl', '') or raw.get('website', ''),
            'industry': raw.get('companyIndustries', [{}])[0].get('localizedName', '') if raw.get('companyIndustries') else '',
            'company_size': raw.get('staffCount', 0),
            'headquarters': raw.get('headquarter', {}),
            'founded_year': raw.get('foundedOn', {}).get('year', ''),
            'specialties': raw.get('specialities', []),
            'logo_url': self._extract_company_logo(raw),
            'follower_count': raw.get('followingInfo', {}).get('followerCount', 0),
        }

    def _normalize_job(self, raw):
        """Normalize job listing."""
        return {
            'job_id': raw.get('trackingUrn', '').split(':')[-1] if raw.get('trackingUrn') else '',
            'title': raw.get('title', ''),
            'company': raw.get('companyName', ''),
            'location': raw.get('formattedLocation', ''),
            'listed_at': raw.get('listedAt', ''),
        }

    def _normalize_scrapin_response(self, raw):
        """Normalize ScrapIn API response."""
        person = raw.get('person', {})
        company = raw.get('company', {})
        return {
            'linkedin_id': person.get('publicIdentifier', ''),
            'full_name': f"{person.get('firstName', '')} {person.get('lastName', '')}".strip(),
            'first_name': person.get('firstName', ''),
            'last_name': person.get('lastName', ''),
            'headline': person.get('headline', ''),
            'summary': person.get('summary', ''),
            'location': person.get('location', ''),
            'photo_url': person.get('photoUrl', ''),
            'profile_url': person.get('linkedInUrl', ''),
            'current_title': person.get('positions', [{}])[0].get('title', '') if person.get('positions') else '',
            'current_company': company.get('name', ''),
            'experience': [
                {
                    'title': p.get('title', ''),
                    'company': p.get('companyName', ''),
                    'start': p.get('startEndDate', {}).get('start', ''),
                    'end': p.get('startEndDate', {}).get('end', ''),
                    'current': p.get('isCurrent', False),
                }
                for p in person.get('positions', [])
            ],
            'education': [
                {
                    'school': e.get('schoolName', ''),
                    'degree': e.get('degreeName', ''),
                    'field': e.get('fieldOfStudy', ''),
                }
                for e in person.get('schools', [])
            ],
            'skills': [],
            'contact_info': {},
            'enriched_at': datetime.utcnow().isoformat() + 'Z',
        }

    # ─── Extraction Helpers ───────────────────────────────────

    def _extract_photo(self, raw):
        """Extract best quality profile photo URL."""
        pics = raw.get('displayPictureUrl', '')
        suffix = raw.get('img_400_400', '') or raw.get('img_200_200', '')
        if pics and suffix:
            return pics + suffix
        return pics or ''

    def _extract_current_title(self, raw):
        """Extract current job title."""
        exp = raw.get('experience', [])
        for e in exp:
            if not e.get('timePeriod', {}).get('endDate'):
                return e.get('title', '')
        return raw.get('headline', '').split(' at ')[0].split(' @ ')[0] if raw.get('headline') else ''

    def _extract_current_company(self, raw):
        """Extract current company name."""
        exp = raw.get('experience', [])
        for e in exp:
            if not e.get('timePeriod', {}).get('endDate'):
                return e.get('companyName', '')
        return ''

    def _extract_experience(self, raw):
        """Extract work experience history."""
        result = []
        for e in raw.get('experience', []):
            tp = e.get('timePeriod', {})
            start = tp.get('startDate', {})
            end = tp.get('endDate', {})
            result.append({
                'title': e.get('title', ''),
                'company': e.get('companyName', ''),
                'company_linkedin': e.get('companyUrn', ''),
                'location': e.get('locationName', ''),
                'description': e.get('description', ''),
                'start_year': start.get('year', ''),
                'start_month': start.get('month', ''),
                'end_year': end.get('year', ''),
                'end_month': end.get('month', ''),
                'current': not bool(end),
            })
        return result

    def _extract_education(self, raw):
        """Extract education history."""
        result = []
        for e in raw.get('education', []):
            tp = e.get('timePeriod', {})
            result.append({
                'school': e.get('schoolName', ''),
                'degree': e.get('degreeName', ''),
                'field': e.get('fieldOfStudy', ''),
                'start_year': tp.get('startDate', {}).get('year', ''),
                'end_year': tp.get('endDate', {}).get('year', ''),
                'activities': e.get('activities', ''),
            })
        return result

    def _extract_certifications(self, raw):
        return [
            {'name': c.get('name', ''), 'authority': c.get('authority', '')}
            for c in raw.get('certifications', [])
        ]

    def _extract_languages(self, raw):
        return [
            {'name': l.get('name', ''), 'proficiency': l.get('proficiency', '')}
            for l in raw.get('languages', [])
        ]

    def _extract_company_logo(self, raw):
        logo = raw.get('logo', {})
        img = logo.get('image', {}).get('com.linkedin.common.VectorImage', {})
        root = img.get('rootUrl', '')
        artifacts = img.get('artifacts', [])
        if root and artifacts:
            best = max(artifacts, key=lambda a: a.get('width', 0))
            return root + best.get('fileIdentifyingUrlPathSegment', '')
        return ''

    # ─── Status ───────────────────────────────────────────────

    def status(self):
        """Get provider status."""
        return {
            'provider': 'linkedin',
            'authenticated': self._authenticated,
            'requests_this_hour': self._request_count,
            'max_requests_per_hour': self.max_requests_per_hour,
            'cache_size': len(self._cache),
            'cache_ttl_days': self.cache_ttl // 86400,
            'has_scrapin_fallback': bool(self.scrapin_key),
            'email_configured': bool(self.email),
        }


# ═══════════════════════════════════════════════════════════════
# FLASK BLUEPRINT — API ENDPOINTS
# ═══════════════════════════════════════════════════════════════

from flask import Blueprint, request as flask_request, jsonify, g

linkedin_bp = Blueprint('linkedin', __name__, url_prefix='/api/v1/linkedin')

_client = LinkedInClient()


def _require_auth(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not getattr(g, 'user_id', None):
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return wrapped


@linkedin_bp.route('/profile', methods=['POST'])
@_require_auth
def linkedin_profile():
    """
    Get LinkedIn profile by public_id or URL.

    POST /api/v1/linkedin/profile
    {
        "public_id": "billy-g"          // or
        "url": "https://linkedin.com/in/billy-g"  // or
        "urn_id": "ACoAAA..."
    }
    """
    data = flask_request.get_json() or {}

    public_id = data.get('public_id', '')
    url = data.get('url', '')
    urn_id = data.get('urn_id', '')

    # Extract public_id from URL
    if url and not public_id:
        match = re.search(r'linkedin\.com/in/([^/?]+)', url)
        if match:
            public_id = match.group(1)

    if not public_id and not urn_id:
        return jsonify({'error': 'public_id, url, or urn_id required'}), 400

    result = _client.get_profile(public_id=public_id or None, urn_id=urn_id or None)

    if 'error' in result and '_source' not in result:
        return jsonify(result), 503

    return jsonify(result)


@linkedin_bp.route('/search', methods=['POST'])
@_require_auth
def linkedin_search():
    """
    Search LinkedIn profiles.

    POST /api/v1/linkedin/search
    {
        "keywords": "software engineer",
        "title": "CTO",
        "company": "Google",
        "location": "San Francisco",
        "limit": 10
    }
    """
    data = flask_request.get_json() or {}
    result = _client.search_people(
        keywords=data.get('keywords'),
        current_company=data.get('company'),
        title=data.get('title'),
        location=data.get('location'),
        limit=min(data.get('limit', 10), 50),
    )
    return jsonify(result)


@linkedin_bp.route('/company', methods=['POST'])
@_require_auth
def linkedin_company():
    """
    Get LinkedIn company profile.

    POST /api/v1/linkedin/company
    { "public_id": "google" }
    """
    data = flask_request.get_json() or {}
    public_id = data.get('public_id', '')
    url = data.get('url', '')

    if url and not public_id:
        match = re.search(r'linkedin\.com/company/([^/?]+)', url)
        if match:
            public_id = match.group(1)

    if not public_id:
        return jsonify({'error': 'public_id or url required'}), 400

    result = _client.get_company(public_id)
    return jsonify(result)


@linkedin_bp.route('/connections', methods=['POST'])
@_require_auth
def linkedin_connections():
    """
    Get 1st degree connections.

    POST /api/v1/linkedin/connections
    { "urn_id": "ACoAAA...", "limit": 50 }
    """
    data = flask_request.get_json() or {}
    urn_id = data.get('urn_id', '')
    if not urn_id:
        return jsonify({'error': 'urn_id required'}), 400

    result = _client.get_connections(urn_id, max_connections=min(data.get('limit', 50), 200))
    return jsonify(result)


@linkedin_bp.route('/jobs', methods=['POST'])
@_require_auth
def linkedin_jobs():
    """
    Search LinkedIn jobs.

    POST /api/v1/linkedin/jobs
    { "keywords": "python developer", "location": "Berlin", "limit": 10 }
    """
    data = flask_request.get_json() or {}
    keywords = data.get('keywords', '')
    if not keywords:
        return jsonify({'error': 'keywords required'}), 400

    result = _client.search_jobs(keywords, location=data.get('location'), limit=min(data.get('limit', 10), 50))
    return jsonify(result)


@linkedin_bp.route('/enrich', methods=['POST'])
@_require_auth
def linkedin_enrich():
    """
    Enrich a ContactIQ contact with LinkedIn data.
    Tries to find the person by name + company, then fetches full profile.

    POST /api/v1/linkedin/enrich
    {
        "contact_id": "abc123",        // optional - updates contact in DB
        "name": "John Doe",
        "company": "Google",
        "email": "john@google.com",    // optional
        "linkedin_url": "https://..."  // optional - direct lookup
    }
    """
    data = flask_request.get_json() or {}
    linkedin_url = data.get('linkedin_url', '')
    name = data.get('name', '')
    company = data.get('company', '')

    # Direct lookup if URL provided
    if linkedin_url:
        match = re.search(r'linkedin\.com/in/([^/?]+)', linkedin_url)
        if match:
            profile = _client.get_profile(public_id=match.group(1))
            return jsonify({
                'enriched': 'error' not in profile,
                'profile': profile,
                'method': 'direct_url',
            })

    # Search by name + company
    if name:
        results = _client.search_people(keywords=name, current_company=company, limit=3)
        matches = results.get('results', [])

        if matches:
            # Get full profile of best match
            best = matches[0]
            if best.get('public_id'):
                profile = _client.get_profile(public_id=best['public_id'])
                return jsonify({
                    'enriched': 'error' not in profile,
                    'profile': profile,
                    'method': 'search_match',
                    'match_confidence': 'high' if len(matches) == 1 else 'medium',
                    'alternatives': matches[1:] if len(matches) > 1 else [],
                })

    return jsonify({
        'enriched': False,
        'error': 'Could not find matching LinkedIn profile',
        'method': 'search_miss',
    })


@linkedin_bp.route('/status', methods=['GET'])
def linkedin_status():
    """Get LinkedIn provider status."""
    return jsonify(_client.status())


# ═══════════════════════════════════════════════════════════════
# AI AGENT TOOL DEFINITIONS
# ═══════════════════════════════════════════════════════════════

LINKEDIN_AGENT_TOOLS = [
    {
        'name': 'linkedin_profile',
        'description': 'Get a full LinkedIn profile by public ID or URL. Returns work history, education, skills, photo, contact info.',
        'parameters': {
            'type': 'object',
            'properties': {
                'public_id': {'type': 'string', 'description': 'LinkedIn vanity URL slug (e.g. "billy-g")'},
                'url': {'type': 'string', 'description': 'Full LinkedIn profile URL'},
            },
        },
    },
    {
        'name': 'linkedin_search',
        'description': 'Search for people on LinkedIn by keywords, title, company, or location.',
        'parameters': {
            'type': 'object',
            'properties': {
                'keywords': {'type': 'string', 'description': 'Search keywords'},
                'title': {'type': 'string', 'description': 'Job title filter'},
                'company': {'type': 'string', 'description': 'Company name filter'},
                'location': {'type': 'string', 'description': 'Location filter'},
                'limit': {'type': 'integer', 'description': 'Max results (default 10)'},
            },
        },
    },
    {
        'name': 'linkedin_company',
        'description': 'Get a LinkedIn company profile with description, size, industry, specialties.',
        'parameters': {
            'type': 'object',
            'properties': {
                'public_id': {'type': 'string', 'description': 'Company LinkedIn slug (e.g. "google")'},
                'url': {'type': 'string', 'description': 'Full company LinkedIn URL'},
            },
        },
    },
    {
        'name': 'linkedin_enrich',
        'description': 'Enrich a contact with LinkedIn data. Searches by name + company, returns full profile.',
        'parameters': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Person full name'},
                'company': {'type': 'string', 'description': 'Current company'},
                'linkedin_url': {'type': 'string', 'description': 'Direct LinkedIn URL (optional)'},
            },
            'required': ['name'],
        },
    },
    {
        'name': 'linkedin_jobs',
        'description': 'Search for jobs on LinkedIn.',
        'parameters': {
            'type': 'object',
            'properties': {
                'keywords': {'type': 'string', 'description': 'Job search keywords'},
                'location': {'type': 'string', 'description': 'Location filter'},
                'limit': {'type': 'integer', 'description': 'Max results (default 10)'},
            },
            'required': ['keywords'],
        },
    },
]


def execute_linkedin_tool(tool_name, arguments):
    """Execute a LinkedIn agent tool. Called from server.py's /agent/tool endpoint."""
    if tool_name == 'linkedin_profile':
        return _client.get_profile(
            public_id=arguments.get('public_id'),
            urn_id=arguments.get('urn_id'),
        )
    elif tool_name == 'linkedin_search':
        return _client.search_people(
            keywords=arguments.get('keywords'),
            title=arguments.get('title'),
            current_company=arguments.get('company'),
            location=arguments.get('location'),
            limit=arguments.get('limit', 10),
        )
    elif tool_name == 'linkedin_company':
        pid = arguments.get('public_id', '')
        url = arguments.get('url', '')
        if url and not pid:
            match = re.search(r'linkedin\.com/company/([^/?]+)', url)
            if match:
                pid = match.group(1)
        return _client.get_company(pid)
    elif tool_name == 'linkedin_enrich':
        return _enrich_via_tool(arguments)
    elif tool_name == 'linkedin_jobs':
        return _client.search_jobs(
            arguments.get('keywords', ''),
            location=arguments.get('location'),
            limit=arguments.get('limit', 10),
        )
    else:
        return {'error': f'Unknown tool: {tool_name}'}


def _enrich_via_tool(args):
    """Agent tool enrichment."""
    url = args.get('linkedin_url', '')
    if url:
        match = re.search(r'linkedin\.com/in/([^/?]+)', url)
        if match:
            return _client.get_profile(public_id=match.group(1))

    name = args.get('name', '')
    company = args.get('company', '')
    if name:
        results = _client.search_people(keywords=name, current_company=company, limit=1)
        matches = results.get('results', [])
        if matches and matches[0].get('public_id'):
            return _client.get_profile(public_id=matches[0]['public_id'])

    return {'error': 'No matching profile found'}


# ═══════════════════════════════════════════════════════════════
# PROVIDER INTERFACE (for providers.py integration)
# ═══════════════════════════════════════════════════════════════

class LinkedInProvider:
    """
    ContactIQ provider interface.
    Add to PROVIDERS dict in providers.py:

        from linkedin_provider import LinkedInProvider
        PROVIDERS['linkedin'] = LinkedInProvider()
    """

    name = 'linkedin'
    provider_type = 'person'  # person + company
    rate_limit = '80/hr (self-hosted) or unlimited (ScrapIn)'
    cost = '$0 (self-hosted) / $0.01+ per profile (ScrapIn)'

    def __init__(self):
        self.client = LinkedInClient()

    def fetch(self, contact_data):
        """
        Fetch LinkedIn data for a contact.
        contact_data: dict with keys like name, email, company, linkedin_url
        Returns: dict with enrichment data
        """
        linkedin_url = contact_data.get('linkedin_url', '') or contact_data.get('linkedin', '')
        name = contact_data.get('name', '') or f"{contact_data.get('first_name', '')} {contact_data.get('last_name', '')}".strip()
        company = contact_data.get('company', '')

        # Direct lookup
        if linkedin_url:
            match = re.search(r'linkedin\.com/in/([^/?]+)', linkedin_url)
            if match:
                profile = self.client.get_profile(public_id=match.group(1))
                if 'error' not in profile:
                    return self._to_enrichment(profile)

        # Search by name
        if name:
            results = self.client.search_people(keywords=name, current_company=company, limit=3)
            matches = results.get('results', [])
            if matches and matches[0].get('public_id'):
                profile = self.client.get_profile(public_id=matches[0]['public_id'])
                if 'error' not in profile:
                    return self._to_enrichment(profile)

        return {'provider': 'linkedin', 'found': False}

    def _to_enrichment(self, profile):
        """Convert LinkedIn profile to standard enrichment format."""
        return {
            'provider': 'linkedin',
            'found': True,
            'data': {
                'full_name': profile.get('full_name', ''),
                'title': profile.get('current_title', ''),
                'company': profile.get('current_company', ''),
                'headline': profile.get('headline', ''),
                'summary': profile.get('summary', ''),
                'location': profile.get('location', ''),
                'country': profile.get('country', ''),
                'industry': profile.get('industry', ''),
                'photo_url': profile.get('photo_url', ''),
                'linkedin_url': profile.get('profile_url', ''),
                'experience': profile.get('experience', []),
                'education': profile.get('education', []),
                'skills': profile.get('skills', []),
                'contact_info': profile.get('contact_info', {}),
                'connection_count': profile.get('connection_count', 0),
                'certifications': profile.get('certifications', []),
                'languages': profile.get('languages', []),
            },
            'source': profile.get('_source', 'linkedin-api'),
            'cached': profile.get('_cached', False),
            'enriched_at': profile.get('enriched_at', ''),
        }

    def test(self):
        """Test provider connectivity."""
        status = self.client.status()
        return {
            'provider': 'linkedin',
            'status': 'ok' if status['authenticated'] or status['has_scrapin_fallback'] else 'disabled',
            'details': status,
        }
