"""
ContactIQ LinkedIn Provider Tests
Run: pytest test_linkedin.py -v
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, os.path.dirname(__file__))
from linkedin_provider import LinkedInClient, LinkedInProvider, linkedin_bp


# ═══════════════════════════════════════════════════════════════
# MOCK DATA
# ═══════════════════════════════════════════════════════════════

MOCK_PROFILE = {
    'public_id': 'billy-g',
    'urn_id': 'ACoAAAA123',
    'firstName': 'Bill',
    'lastName': 'Gates',
    'headline': 'Co-chair, Bill & Melinda Gates Foundation',
    'summary': 'Co-chair of the Bill & Melinda Gates Foundation.',
    'industryName': 'Philanthropy',
    'locationName': 'Seattle, Washington',
    'geoCountryName': 'United States',
    'displayPictureUrl': 'https://media.licdn.com/dms/image/',
    'img_400_400': '/v2/photo_400.jpg',
    'connections': 500,
    'followerCount': 35000000,
    'experience': [
        {
            'title': 'Co-chair',
            'companyName': 'Bill & Melinda Gates Foundation',
            'companyUrn': 'urn:li:company:8736',
            'locationName': 'Seattle',
            'description': 'Leading global health and education initiatives.',
            'timePeriod': {
                'startDate': {'year': 2000, 'month': 1},
                'endDate': {},
            },
        },
        {
            'title': 'Co-founder & Technology Advisor',
            'companyName': 'Microsoft',
            'companyUrn': 'urn:li:company:1035',
            'timePeriod': {
                'startDate': {'year': 1975, 'month': 4},
                'endDate': {'year': 2020, 'month': 3},
            },
        },
    ],
    'education': [
        {
            'schoolName': 'Harvard University',
            'degreeName': '',
            'fieldOfStudy': 'Computer Science',
            'timePeriod': {
                'startDate': {'year': 1973},
                'endDate': {'year': 1975},
            },
            'activities': '',
        },
    ],
    'certifications': [],
    'languages': [
        {'name': 'English', 'proficiency': 'NATIVE_OR_BILINGUAL'},
    ],
}

MOCK_CONTACT_INFO = {
    'email_address': 'bill@gatesfoundation.org',
    'phone_numbers': [{'number': '+1-555-0100', 'type': 'MOBILE'}],
    'websites': [{'url': 'https://www.gatesnotes.com'}],
    'twitter': {'name': 'BillGates'},
    'ims': [],
}

MOCK_SKILLS = [
    {'name': 'Software Development', 'endorsementCount': 99},
    {'name': 'Philanthropy', 'endorsementCount': 99},
    {'name': 'Strategy', 'endorsementCount': 85},
]

MOCK_SEARCH = [
    {'urn_id': 'ACoAAAA123', 'public_id': 'billy-g', 'name': 'Bill Gates',
     'jobtitle': 'Co-chair at Gates Foundation', 'location': 'Seattle'},
    {'urn_id': 'ACoAAAA456', 'public_id': 'bill-gates-2', 'name': 'Bill Gates',
     'jobtitle': 'Software Engineer', 'location': 'Austin'},
]

MOCK_COMPANY = {
    'name': 'Microsoft',
    'universalName': 'microsoft',
    'description': 'Technology company',
    'companyPageUrl': 'https://www.microsoft.com',
    'companyIndustries': [{'localizedName': 'Technology'}],
    'staffCount': 220000,
    'headquarter': {'city': 'Redmond', 'country': 'US'},
    'foundedOn': {'year': 1975},
    'specialities': ['Software', 'Cloud', 'AI'],
    'logo': {},
    'followingInfo': {'followerCount': 20000000},
}


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset LinkedInClient singleton between tests."""
    LinkedInClient._instance = None
    os.environ['LINKEDIN_EMAIL'] = 'test@test.com'
    os.environ['LINKEDIN_PASSWORD'] = 'testpass'
    os.environ['LINKEDIN_RATE_LIMIT'] = '100'
    os.environ['LINKEDIN_DELAY'] = '0'  # No delay in tests
    os.environ['LINKEDIN_CACHE_TTL'] = '3600'
    yield
    for key in ['LINKEDIN_EMAIL', 'LINKEDIN_PASSWORD', 'LINKEDIN_RATE_LIMIT',
                'LINKEDIN_DELAY', 'LINKEDIN_CACHE_TTL', 'SCRAPIN_API_KEY']:
        os.environ.pop(key, None)


@pytest.fixture
def mock_linkedin_api():
    """Mock the linkedin_api.Linkedin class."""
    with patch('linkedin_provider.LinkedInClient._authenticate') as mock_auth:
        mock_auth.return_value = True
        client = LinkedInClient()
        client._authenticated = True

        mock_api = MagicMock()
        mock_api.get_profile.return_value = MOCK_PROFILE
        mock_api.get_profile_contact_info.return_value = MOCK_CONTACT_INFO
        mock_api.get_profile_skills.return_value = MOCK_SKILLS
        mock_api.search_people.return_value = MOCK_SEARCH
        mock_api.get_company.return_value = MOCK_COMPANY
        mock_api.get_profile_connections.return_value = MOCK_SEARCH[:1]
        mock_api.search_jobs.return_value = [
            {'trackingUrn': 'urn:li:job:123', 'title': 'Python Dev',
             'companyName': 'Google', 'formattedLocation': 'NYC'},
        ]

        client._api = mock_api
        yield client


@pytest.fixture
def app(mock_linkedin_api):
    """Flask test app."""
    from flask import Flask, g
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(linkedin_bp)

    @app.before_request
    def set_context():
        g.user_id = 'test_user'

    return app


@pytest.fixture
def web(app):
    return app.test_client()


# ═══════════════════════════════════════════════════════════════
# CLIENT TESTS
# ═══════════════════════════════════════════════════════════════

class TestLinkedInClient:

    def test_get_profile(self, mock_linkedin_api):
        result = mock_linkedin_api.get_profile(public_id='billy-g')
        assert result['full_name'] == 'Bill Gates'
        assert result['current_title'] == 'Co-chair'
        assert result['current_company'] == 'Bill & Melinda Gates Foundation'
        assert result['linkedin_id'] == 'billy-g'
        assert result['_source'] == 'linkedin-api'

    def test_profile_contact_info(self, mock_linkedin_api):
        result = mock_linkedin_api.get_profile(public_id='billy-g')
        assert result['contact_info']['email'] == 'bill@gatesfoundation.org'
        assert result['contact_info']['twitter'] == 'BillGates'

    def test_profile_skills(self, mock_linkedin_api):
        result = mock_linkedin_api.get_profile(public_id='billy-g')
        assert len(result['skills']) == 3
        assert result['skills'][0]['name'] == 'Software Development'

    def test_profile_experience(self, mock_linkedin_api):
        result = mock_linkedin_api.get_profile(public_id='billy-g')
        assert len(result['experience']) == 2
        assert result['experience'][0]['company'] == 'Bill & Melinda Gates Foundation'
        assert result['experience'][0]['current'] is True
        assert result['experience'][1]['company'] == 'Microsoft'
        assert result['experience'][1]['current'] is False

    def test_profile_education(self, mock_linkedin_api):
        result = mock_linkedin_api.get_profile(public_id='billy-g')
        assert len(result['education']) == 1
        assert result['education'][0]['school'] == 'Harvard University'

    def test_profile_caching(self, mock_linkedin_api):
        r1 = mock_linkedin_api.get_profile(public_id='billy-g')
        assert r1.get('_cached') is not True

        r2 = mock_linkedin_api.get_profile(public_id='billy-g')
        assert r2.get('_cached') is True

    def test_search_people(self, mock_linkedin_api):
        result = mock_linkedin_api.search_people(keywords='Bill Gates')
        assert result['count'] == 2
        assert result['results'][0]['name'] == 'Bill Gates'

    def test_get_company(self, mock_linkedin_api):
        result = mock_linkedin_api.get_company('microsoft')
        assert result['name'] == 'Microsoft'
        assert result['company_size'] == 220000

    def test_search_jobs(self, mock_linkedin_api):
        result = mock_linkedin_api.search_jobs('python developer')
        assert result['count'] == 1
        assert result['jobs'][0]['title'] == 'Python Dev'

    def test_rate_limiting(self, mock_linkedin_api):
        mock_linkedin_api.max_requests_per_hour = 3
        mock_linkedin_api._request_count = 0
        mock_linkedin_api._window_start = 0  # Force fresh window

        for i in range(3):
            assert mock_linkedin_api._check_rate_limit() is True

        assert mock_linkedin_api._check_rate_limit() is False

    def test_status(self, mock_linkedin_api):
        status = mock_linkedin_api.status()
        assert status['provider'] == 'linkedin'
        assert status['authenticated'] is True
        assert status['email_configured'] is True


# ═══════════════════════════════════════════════════════════════
# API ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════

class TestLinkedInAPI:

    def test_get_profile_by_id(self, web):
        r = web.post('/api/v1/linkedin/profile', json={'public_id': 'billy-g'})
        assert r.status_code == 200
        data = r.get_json()
        assert data['full_name'] == 'Bill Gates'

    def test_get_profile_by_url(self, web):
        r = web.post('/api/v1/linkedin/profile', json={
            'url': 'https://linkedin.com/in/billy-g',
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data['linkedin_id'] == 'billy-g'

    def test_profile_missing_params(self, web):
        r = web.post('/api/v1/linkedin/profile', json={})
        assert r.status_code == 400

    def test_search(self, web):
        r = web.post('/api/v1/linkedin/search', json={'keywords': 'Bill Gates'})
        assert r.status_code == 200
        data = r.get_json()
        assert data['count'] >= 1

    def test_company(self, web):
        r = web.post('/api/v1/linkedin/company', json={'public_id': 'microsoft'})
        assert r.status_code == 200
        data = r.get_json()
        assert data['name'] == 'Microsoft'

    def test_company_by_url(self, web):
        r = web.post('/api/v1/linkedin/company', json={
            'url': 'https://linkedin.com/company/microsoft',
        })
        assert r.status_code == 200

    def test_enrich_by_url(self, web):
        r = web.post('/api/v1/linkedin/enrich', json={
            'linkedin_url': 'https://linkedin.com/in/billy-g',
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data['enriched'] is True
        assert data['method'] == 'direct_url'

    def test_enrich_by_name(self, web):
        r = web.post('/api/v1/linkedin/enrich', json={
            'name': 'Bill Gates',
            'company': 'Gates Foundation',
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data['enriched'] is True
        assert data['method'] == 'search_match'

    def test_jobs_search(self, web):
        r = web.post('/api/v1/linkedin/jobs', json={'keywords': 'python'})
        assert r.status_code == 200
        data = r.get_json()
        assert data['count'] >= 1

    def test_status(self, web):
        r = web.get('/api/v1/linkedin/status')
        assert r.status_code == 200
        data = r.get_json()
        assert data['provider'] == 'linkedin'


# ═══════════════════════════════════════════════════════════════
# PROVIDER INTERFACE TESTS
# ═══════════════════════════════════════════════════════════════

class TestLinkedInProviderInterface:

    def test_fetch_by_url(self, mock_linkedin_api):
        provider = LinkedInProvider()
        provider.client = mock_linkedin_api

        result = provider.fetch({
            'linkedin_url': 'https://linkedin.com/in/billy-g',
        })
        assert result['found'] is True
        assert result['provider'] == 'linkedin'
        assert result['data']['full_name'] == 'Bill Gates'
        assert result['data']['title'] == 'Co-chair'
        assert result['data']['company'] == 'Bill & Melinda Gates Foundation'

    def test_fetch_by_name(self, mock_linkedin_api):
        provider = LinkedInProvider()
        provider.client = mock_linkedin_api

        result = provider.fetch({
            'name': 'Bill Gates',
            'company': 'Gates Foundation',
        })
        assert result['found'] is True
        assert result['data']['linkedin_url'] == 'https://linkedin.com/in/billy-g'

    def test_fetch_not_found(self, mock_linkedin_api):
        mock_linkedin_api._api.search_people.return_value = []
        provider = LinkedInProvider()
        provider.client = mock_linkedin_api

        result = provider.fetch({'name': 'Nobody McFakename'})
        assert result['found'] is False

    def test_provider_test(self, mock_linkedin_api):
        provider = LinkedInProvider()
        provider.client = mock_linkedin_api

        result = provider.test()
        assert result['status'] == 'ok'


# ═══════════════════════════════════════════════════════════════
# AGENT TOOL TESTS
# ═══════════════════════════════════════════════════════════════

class TestAgentTools:

    def test_tool_definitions(self):
        from linkedin_provider import LINKEDIN_AGENT_TOOLS
        names = [t['name'] for t in LINKEDIN_AGENT_TOOLS]
        assert 'linkedin_profile' in names
        assert 'linkedin_search' in names
        assert 'linkedin_company' in names
        assert 'linkedin_enrich' in names
        assert 'linkedin_jobs' in names

    def test_execute_profile_tool(self, mock_linkedin_api):
        from linkedin_provider import execute_linkedin_tool
        # Patch the module-level _client
        import linkedin_provider
        linkedin_provider._client = mock_linkedin_api

        result = execute_linkedin_tool('linkedin_profile', {'public_id': 'billy-g'})
        assert result['full_name'] == 'Bill Gates'

    def test_execute_search_tool(self, mock_linkedin_api):
        from linkedin_provider import execute_linkedin_tool
        import linkedin_provider
        linkedin_provider._client = mock_linkedin_api

        result = execute_linkedin_tool('linkedin_search', {'keywords': 'CTO'})
        assert result['count'] >= 1

    def test_execute_unknown_tool(self, mock_linkedin_api):
        from linkedin_provider import execute_linkedin_tool
        result = execute_linkedin_tool('linkedin_nonexistent', {})
        assert 'error' in result
