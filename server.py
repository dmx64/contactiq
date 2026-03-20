#!/usr/bin/env python3
"""
ContactIQ Backend Server
Comprehensive Contact Intelligence Platform with 56 API endpoints
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sqlite3
import hashlib
import uuid
import os
import json
import time
from datetime import datetime, timedelta
import logging
from functools import wraps
import threading
import subprocess
import requests
from providers import ContactProviders, EnrichmentPipeline
from osint_contact import OSINTEngine
from enrichment_router import enrich_person as route_enrich_person, adapter_chain_enabled
from enrichment_telemetry import (
    build_hourly_trend_alerts,
    build_hourly_trends,
    build_provider_latency_summary,
    build_provider_error_breakdown,
    build_telemetry_overview,
    build_telemetry_row,
    compute_latency_p95_ms,
    resolve_trend_alert_config,
)

# Flask App Configuration
app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'contactiq-dev-key-2024')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=30)

# Extensions
cors = CORS(app)
jwt = JWTManager(app)
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["1000 per hour"]
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize providers and OSINT
enrichment_pipeline = EnrichmentPipeline()
providers = ContactProviders()
osint_engine = OSINTEngine()

# Database initialization
def init_database():
    """Initialize SQLite database with all tables"""
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            tier TEXT DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')
    
    # Contacts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            email TEXT,
            phone TEXT,
            name TEXT,
            company TEXT,
            enriched_data TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Caller ID logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS caller_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            phone TEXT NOT NULL,
            result TEXT,
            spam_score REAL,
            carrier TEXT,
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # OSINT investigations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS osint_investigations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            query TEXT NOT NULL,
            query_type TEXT NOT NULL,
            results TEXT,
            tools_used TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # QR Cards table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS qr_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            title TEXT,
            company TEXT,
            email TEXT,
            phone TEXT,
            website TEXT,
            card_data TEXT,
            qr_code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Alerts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            contact_id INTEGER,
            alert_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            severity TEXT DEFAULT 'info',
            read_status BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # API usage tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint TEXT NOT NULL,
            provider TEXT,
            tokens_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Adapter-chain telemetry tracking (rollout visibility)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS enrichment_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            request_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            chain TEXT,
            status TEXT,
            selected_provider TEXT,
            fallback_used BOOLEAN DEFAULT FALSE,
            attempt_count INTEGER DEFAULT 0,
            total_latency_ms REAL DEFAULT 0,
            error TEXT,
            attempts_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_enrichment_telemetry_request ON enrichment_telemetry(request_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_enrichment_telemetry_created ON enrichment_telemetry(created_at)')
    
    conn.commit()
    conn.close()

# Authentication decorators
def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        conn = sqlite3.connect('contactiq.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, email, tier FROM users WHERE api_key = ?', (api_key,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'error': 'Invalid API key'}), 401
        
        request.user_id = user[0]
        request.user_email = user[1]
        request.user_tier = user[2]
        return f(*args, **kwargs)
    return decorated_function

# Utility functions
def generate_api_key():
    """Generate unique API key"""
    return f"ciq_{uuid.uuid4().hex}"

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def log_api_usage(user_id, endpoint, provider=None, tokens=0):
    """Log API usage for analytics"""
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO api_usage (user_id, endpoint, provider, tokens_used)
        VALUES (?, ?, ?, ?)
    ''', (user_id, endpoint, provider, tokens))
    conn.commit()
    conn.close()


def persist_enrichment_telemetry(row):
    """Persist adapter-chain telemetry without breaking request flow on DB errors."""
    if not row:
        return False

    try:
        conn = sqlite3.connect('contactiq.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO enrichment_telemetry (
                user_id,
                request_id,
                mode,
                chain,
                status,
                selected_provider,
                fallback_used,
                attempt_count,
                total_latency_ms,
                error,
                attempts_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            row.get('user_id'),
            row.get('request_id'),
            row.get('mode'),
            row.get('chain'),
            row.get('status'),
            row.get('selected_provider'),
            row.get('fallback_used'),
            row.get('attempt_count'),
            row.get('total_latency_ms'),
            row.get('error'),
            row.get('attempts_json'),
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        logger.warning('Failed to persist enrichment telemetry: %s', exc)
        return False

# =============================================================================
# AUTHENTICATION ENDPOINTS (8 endpoints)
# =============================================================================

@app.route('/api/v1/auth/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    """Register new user"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    
    # Check if user exists
    cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'error': 'User already exists'}), 409
    
    # Create user
    api_key = generate_api_key()
    password_hash = hash_password(password)
    
    cursor.execute('''
        INSERT INTO users (email, password_hash, api_key)
        VALUES (?, ?, ?)
    ''', (email, password_hash, api_key))
    
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Create JWT token
    access_token = create_access_token(identity=user_id)
    
    log_api_usage(user_id, 'auth/register')
    
    return jsonify({
        'user_id': user_id,
        'email': email,
        'api_key': api_key,
        'access_token': access_token,
        'tier': 'free'
    }), 201

@app.route('/api/v1/auth/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """User login"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    cursor.execute('''
        SELECT id, email, api_key, tier FROM users 
        WHERE email = ? AND password_hash = ?
    ''', (email, password_hash))
    
    user = cursor.fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Update last login
    cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user[0],))
    conn.commit()
    conn.close()
    
    access_token = create_access_token(identity=user[0])
    
    log_api_usage(user[0], 'auth/login')
    
    return jsonify({
        'user_id': user[0],
        'email': user[1],
        'api_key': user[2],
        'access_token': access_token,
        'tier': user[3]
    })

@app.route('/api/v1/auth/refresh', methods=['POST'])
@jwt_required()
def refresh():
    """Refresh JWT token"""
    current_user = get_jwt_identity()
    new_token = create_access_token(identity=current_user)
    
    log_api_usage(current_user, 'auth/refresh')
    
    return jsonify({'access_token': new_token})

@app.route('/api/v1/auth/profile', methods=['GET'])
@api_key_required
def get_profile():
    """Get user profile"""
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT email, tier, created_at, last_login,
        (SELECT COUNT(*) FROM contacts WHERE user_id = ?) as total_contacts,
        (SELECT COUNT(*) FROM caller_logs WHERE user_id = ?) as caller_queries,
        (SELECT COUNT(*) FROM osint_investigations WHERE user_id = ?) as osint_queries
        FROM users WHERE id = ?
    ''', (request.user_id, request.user_id, request.user_id, request.user_id))
    
    profile = cursor.fetchone()
    conn.close()
    
    log_api_usage(request.user_id, 'auth/profile')
    
    return jsonify({
        'email': profile[0],
        'tier': profile[1],
        'created_at': profile[2],
        'last_login': profile[3],
        'stats': {
            'total_contacts': profile[4],
            'caller_queries': profile[5],
            'osint_queries': profile[6]
        }
    })

@app.route('/api/v1/auth/change-password', methods=['PUT'])
@api_key_required
def change_password():
    """Change user password"""
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return jsonify({'error': 'Current and new password required'}), 400
    
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    
    # Verify current password
    current_hash = hash_password(current_password)
    cursor.execute('SELECT id FROM users WHERE id = ? AND password_hash = ?', 
                  (request.user_id, current_hash))
    
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Current password incorrect'}), 401
    
    # Update password
    new_hash = hash_password(new_password)
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', 
                  (new_hash, request.user_id))
    conn.commit()
    conn.close()
    
    log_api_usage(request.user_id, 'auth/change-password')
    
    return jsonify({'message': 'Password updated successfully'})

@app.route('/api/v1/auth/regenerate-api-key', methods=['PUT'])
@api_key_required
def regenerate_api_key():
    """Regenerate API key"""
    new_api_key = generate_api_key()
    
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET api_key = ? WHERE id = ?', 
                  (new_api_key, request.user_id))
    conn.commit()
    conn.close()
    
    log_api_usage(request.user_id, 'auth/regenerate-api-key')
    
    return jsonify({'api_key': new_api_key})

@app.route('/api/v1/auth/upgrade-tier', methods=['PUT'])
@api_key_required
def upgrade_tier():
    """Upgrade user tier"""
    data = request.get_json()
    new_tier = data.get('tier')
    
    if new_tier not in ['free', 'pro', 'enterprise']:
        return jsonify({'error': 'Invalid tier'}), 400
    
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET tier = ? WHERE id = ?', 
                  (new_tier, request.user_id))
    conn.commit()
    conn.close()
    
    log_api_usage(request.user_id, 'auth/upgrade-tier')
    
    return jsonify({'tier': new_tier, 'message': 'Tier updated successfully'})

@app.route('/api/v1/auth/delete-account', methods=['DELETE'])
@api_key_required
def delete_account():
    """Delete user account"""
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    
    # Delete all user data
    tables = ['contacts', 'caller_logs', 'osint_investigations', 
              'qr_cards', 'alerts', 'api_usage']
    
    for table in tables:
        cursor.execute(f'DELETE FROM {table} WHERE user_id = ?', (request.user_id,))
    
    cursor.execute('DELETE FROM users WHERE id = ?', (request.user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Account deleted successfully'})

# =============================================================================
# CONTACTS ENDPOINTS (12 endpoints)
# =============================================================================

@app.route('/api/v1/contacts', methods=['GET'])
@api_key_required
def get_contacts():
    """Get all user contacts with search and pagination"""
    page = int(request.args.get('page', 1))
    limit = min(int(request.args.get('limit', 50)), 100)
    search = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'created_at')
    order = request.args.get('order', 'desc').upper()
    
    offset = (page - 1) * limit
    
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    
    # Build query with search
    where_clause = 'WHERE user_id = ?'
    params = [request.user_id]
    
    if search:
        where_clause += ' AND (name LIKE ? OR email LIKE ? OR company LIKE ?)'
        search_term = f'%{search}%'
        params.extend([search_term, search_term, search_term])
    
    # Count total
    cursor.execute(f'SELECT COUNT(*) FROM contacts {where_clause}', params)
    total = cursor.fetchone()[0]
    
    # Get contacts
    query = f'''
        SELECT id, email, phone, name, company, source, created_at, updated_at
        FROM contacts {where_clause}
        ORDER BY {sort_by} {order}
        LIMIT ? OFFSET ?
    '''
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    contacts = cursor.fetchall()
    conn.close()
    
    log_api_usage(request.user_id, 'contacts/list')
    
    return jsonify({
        'contacts': [
            {
                'id': c[0], 'email': c[1], 'phone': c[2], 
                'name': c[3], 'company': c[4], 'source': c[5],
                'created_at': c[6], 'updated_at': c[7]
            }
            for c in contacts
        ],
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'pages': (total + limit - 1) // limit
        }
    })

@app.route('/api/v1/contacts', methods=['POST'])
@api_key_required
def create_contact():
    """Create new contact"""
    data = request.get_json()
    required = ['email']
    
    if not all(field in data for field in required):
        return jsonify({'error': 'Email is required'}), 400
    
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    
    # Check for duplicate
    cursor.execute('SELECT id FROM contacts WHERE user_id = ? AND email = ?', 
                  (request.user_id, data['email']))
    if cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Contact already exists'}), 409
    
    cursor.execute('''
        INSERT INTO contacts (user_id, email, phone, name, company, source)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (request.user_id, data['email'], data.get('phone'), 
          data.get('name'), data.get('company'), 'manual'))
    
    contact_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    log_api_usage(request.user_id, 'contacts/create')
    
    return jsonify({'contact_id': contact_id, 'message': 'Contact created'}), 201

@app.route('/api/v1/contacts/<int:contact_id>', methods=['GET'])
@api_key_required
def get_contact(contact_id):
    """Get single contact with enriched data"""
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, email, phone, name, company, enriched_data, source, 
               created_at, updated_at
        FROM contacts 
        WHERE id = ? AND user_id = ?
    ''', (contact_id, request.user_id))
    
    contact = cursor.fetchone()
    conn.close()
    
    if not contact:
        return jsonify({'error': 'Contact not found'}), 404
    
    enriched_data = json.loads(contact[5]) if contact[5] else {}
    
    log_api_usage(request.user_id, 'contacts/get')
    
    return jsonify({
        'id': contact[0],
        'email': contact[1],
        'phone': contact[2],
        'name': contact[3],
        'company': contact[4],
        'enriched_data': enriched_data,
        'source': contact[6],
        'created_at': contact[7],
        'updated_at': contact[8]
    })

# =============================================================================
# ENRICHMENT ENDPOINTS (feature-flagged adapter chain rollout)
# =============================================================================

@app.route('/api/v1/enrichment/person', methods=['POST'])
@api_key_required
def enrich_person_contact():
    """
    Enrich a person profile using either:
    - legacy pipeline (default)
    - provider adapter fallback chain (when feature flag is enabled)

    Feature flag:
      CONTACTIQ_ENABLE_ADAPTER_CHAIN=true

    Request override:
      {"force_adapter_chain": true|false}
    """
    request_id = f"enr_{uuid.uuid4().hex[:12]}"
    data = request.get_json() or {}
    full_name = data.get('full_name') or data.get('name')
    email = data.get('email')

    if not full_name and not email:
        return jsonify({'error': 'full_name or email is required'}), 400

    force_raw = data.get('force_adapter_chain')
    force_adapter_chain = None
    if isinstance(force_raw, bool):
        force_adapter_chain = force_raw
    elif isinstance(force_raw, str):
        lowered = force_raw.strip().lower()
        if lowered in {'true', '1', 'yes', 'on'}:
            force_adapter_chain = True
        elif lowered in {'false', '0', 'no', 'off'}:
            force_adapter_chain = False

    contact = {
        'full_name': full_name,
        'email': email,
        'company': data.get('company'),
    }

    enrichment = route_enrich_person(
        contact,
        force_adapter_chain=force_adapter_chain,
        pipeline=enrichment_pipeline,
    )

    mode = enrichment['mode']
    result = enrichment['result']

    telemetry_summary = None
    telemetry_persisted = False

    telemetry_row = build_telemetry_row(
        user_id=request.user_id,
        request_id=request_id,
        mode=mode,
        result=result,
    )
    if telemetry_row:
        telemetry_summary = build_provider_latency_summary(result)
        telemetry_persisted = persist_enrichment_telemetry(telemetry_row)

    logger.info(
        'enrichment_person_completed request_id=%s mode=%s selected_provider=%s',
        request_id,
        mode,
        result.get('selected_provider') if isinstance(result, dict) else None,
    )

    log_api_usage(request.user_id, 'enrichment/person', provider=mode)

    payload = {
        'status': 'completed',
        'request_id': request_id,
        'mode': mode,
        'feature_flags': {
            'CONTACTIQ_ENABLE_ADAPTER_CHAIN': adapter_chain_enabled(),
            'force_adapter_chain': force_adapter_chain,
        },
        'result': result,
    }

    if telemetry_summary is not None:
        payload['telemetry'] = {
            'persisted': telemetry_persisted,
            'chain': telemetry_summary.get('chain'),
            'status': telemetry_summary.get('status'),
            'selected_provider': telemetry_summary.get('selected_provider'),
            'fallback_used': telemetry_summary.get('fallback_used'),
            'attempt_count': telemetry_summary.get('attempt_count'),
            'failed_attempt_count': telemetry_summary.get('failed_attempt_count'),
            'total_latency_ms': telemetry_summary.get('total_latency_ms'),
            'provider_path': telemetry_summary.get('provider_path'),
        }

    return jsonify(payload)


@app.route('/api/v1/enrichment/telemetry', methods=['GET'])
@api_key_required
def get_enrichment_telemetry():
    """Read adapter-chain telemetry rollup and recent request entries."""
    limit_raw = request.args.get('limit', '20')
    since_hours_raw = request.args.get('since_hours', '24')
    chain = (request.args.get('chain') or '').strip() or None

    try:
        limit = max(1, min(int(limit_raw), 100))
    except ValueError:
        return jsonify({'error': 'limit must be an integer'}), 400

    try:
        since_hours = max(1, min(int(since_hours_raw), 24 * 14))
    except ValueError:
        return jsonify({'error': 'since_hours must be an integer'}), 400

    try:
        trend_alert_config_state = resolve_trend_alert_config(
            query_params=request.args,
            env=os.environ,
            chain=chain,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    trend_alert_config = trend_alert_config_state['config']

    where_clauses = ["user_id = ?", "mode = 'adapter_chain'", "created_at >= datetime('now', ?)"]
    params = [request.user_id, f'-{since_hours} hours']

    if chain:
        where_clauses.append('chain = ?')
        params.append(chain)

    where_sql = ' AND '.join(where_clauses)

    try:
        conn = sqlite3.connect('contactiq.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT
                COUNT(*) AS total_requests,
                SUM(CASE WHEN fallback_used = 1 THEN 1 ELSE 0 END) AS fallback_requests,
                SUM(CASE WHEN LOWER(COALESCE(status, '')) IN ('success', 'partial', 'mock') THEN 1 ELSE 0 END) AS successful_requests,
                AVG(attempt_count) AS avg_attempt_count,
                AVG(total_latency_ms) AS avg_latency_ms
            FROM enrichment_telemetry
            WHERE {where_sql}
        ''', params)
        aggregate = cursor.fetchone() or {}

        cursor.execute(f'''
            SELECT selected_provider, COUNT(*) AS request_count
            FROM enrichment_telemetry
            WHERE {where_sql}
              AND selected_provider IS NOT NULL
              AND selected_provider != ''
            GROUP BY selected_provider
            ORDER BY request_count DESC
            LIMIT 5
        ''', params)
        top_providers = [
            {
                'provider': row['selected_provider'],
                'request_count': int(row['request_count'] or 0),
            }
            for row in cursor.fetchall()
        ]

        cursor.execute(f'''
            SELECT total_latency_ms
            FROM enrichment_telemetry
            WHERE {where_sql}
              AND total_latency_ms IS NOT NULL
        ''', params)
        latency_values = [float(row['total_latency_ms'] or 0.0) for row in cursor.fetchall()]

        cursor.execute(f'''
            SELECT attempts_json
            FROM enrichment_telemetry
            WHERE {where_sql}
              AND attempts_json IS NOT NULL
              AND attempts_json != ''
        ''', params)
        attempts_payloads = [row['attempts_json'] for row in cursor.fetchall()]

        cursor.execute(f'''
            SELECT created_at, status, fallback_used, total_latency_ms
            FROM enrichment_telemetry
            WHERE {where_sql}
              AND created_at IS NOT NULL
            ORDER BY created_at ASC
        ''', params)
        trend_rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute(f'''
            SELECT
                request_id,
                chain,
                status,
                selected_provider,
                fallback_used,
                attempt_count,
                total_latency_ms,
                error,
                created_at
            FROM enrichment_telemetry
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ?
        ''', [*params, limit])
        recent_rows = cursor.fetchall()

        conn.close()
    except Exception as exc:
        logger.warning('Failed to read enrichment telemetry: %s', exc)
        return jsonify({'error': 'Failed to read telemetry'}), 500

    hourly_trends = build_hourly_trends(trend_rows, max_points=min(max(since_hours, 1), 168))
    trend_alerts = build_hourly_trend_alerts(
        hourly_trends,
        **trend_alert_config,
    )

    overview = build_telemetry_overview(
        total_requests=aggregate['total_requests'] if aggregate else 0,
        fallback_requests=aggregate['fallback_requests'] if aggregate else 0,
        successful_requests=aggregate['successful_requests'] if aggregate else 0,
        avg_attempt_count=aggregate['avg_attempt_count'] if aggregate else 0.0,
        avg_latency_ms=aggregate['avg_latency_ms'] if aggregate else 0.0,
        latency_p95_ms=compute_latency_p95_ms(latency_values),
        top_providers=top_providers,
        provider_error_breakdown=build_provider_error_breakdown(attempts_payloads, top_n=5),
        hourly_trends=hourly_trends,
        trend_alerts=trend_alerts,
    )

    recent = [
        {
            'request_id': row['request_id'],
            'chain': row['chain'],
            'status': row['status'],
            'selected_provider': row['selected_provider'],
            'fallback_used': bool(row['fallback_used']),
            'attempt_count': int(row['attempt_count'] or 0),
            'total_latency_ms': round(float(row['total_latency_ms'] or 0.0), 2),
            'error': row['error'],
            'created_at': row['created_at'],
        }
        for row in recent_rows
    ]

    log_api_usage(request.user_id, 'enrichment/telemetry', provider='adapter_chain')

    return jsonify({
        'status': 'ok',
        'window': {
            'since_hours': since_hours,
            'chain': chain,
            'limit': limit,
            'trend_alert_config': trend_alert_config,
            'trend_alert_overrides': trend_alert_config_state['applied'],
        },
        'overview': overview,
        'recent': recent,
    })

# ═══════════════════════════════════════════════════════════
# CONTACTS — remaining 9 endpoints
# ═══════════════════════════════════════════════════════════

@app.route('/api/v1/contacts/<int:contact_id>', methods=['PUT'])
@api_key_required
def update_contact(contact_id):
    """Update an existing contact."""
    data = request.get_json() or {}
    log_api_usage(request.user_id, 'contacts/update')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM contacts WHERE id = ? AND user_id = ?', (contact_id, request.user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Contact not found'}), 404
    fields = []
    values = []
    for field in ['email', 'phone', 'name', 'company', 'source']:
        if field in data:
            fields.append(f'{field} = ?')
            values.append(data[field])
    if 'enriched_data' in data:
        fields.append('enriched_data = ?')
        values.append(json.dumps(data['enriched_data']) if isinstance(data['enriched_data'], dict) else data['enriched_data'])
    if not fields:
        conn.close()
        return jsonify({'error': 'No fields to update'}), 400
    fields.append('updated_at = CURRENT_TIMESTAMP')
    values.extend([contact_id, request.user_id])
    cursor.execute(f'UPDATE contacts SET {", ".join(fields)} WHERE id = ? AND user_id = ?', values)
    conn.commit()
    conn.close()
    return jsonify({'status': 'updated', 'id': contact_id})


@app.route('/api/v1/contacts/<int:contact_id>', methods=['DELETE'])
@api_key_required
def delete_contact(contact_id):
    """Delete a contact."""
    log_api_usage(request.user_id, 'contacts/delete')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM contacts WHERE id = ? AND user_id = ?', (contact_id, request.user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Contact not found'}), 404
    cursor.execute('DELETE FROM contacts WHERE id = ? AND user_id = ?', (contact_id, request.user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'deleted', 'id': contact_id})


@app.route('/api/v1/contacts/<int:contact_id>/enrich', methods=['POST'])
@api_key_required
def enrich_contact_endpoint(contact_id):
    """Trigger enrichment for a contact."""
    log_api_usage(request.user_id, 'contacts/enrich')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM contacts WHERE id = ? AND user_id = ?', (contact_id, request.user_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Contact not found'}), 404
    columns = [d[0] for d in cursor.description]
    contact = dict(zip(columns, row))
    contact_data = {
        'full_name': contact.get('name', ''),
        'email': contact.get('email'),
        'phone': contact.get('phone'),
        'company': contact.get('company'),
    }
    result = enrichment_pipeline.enrich_contact(contact_data)
    cursor.execute(
        'UPDATE contacts SET enriched_data = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?',
        (json.dumps(result), contact_id, request.user_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'status': 'enriched', 'id': contact_id, 'result': result})


@app.route('/api/v1/contacts/<int:contact_id>/history', methods=['GET'])
@api_key_required
def get_contact_history(contact_id):
    """Get enrichment history for a contact."""
    log_api_usage(request.user_id, 'contacts/history')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM contacts WHERE id = ? AND user_id = ?', (contact_id, request.user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Contact not found'}), 404
    cursor.execute(
        'SELECT id, endpoint, provider, tokens_used, created_at FROM api_usage WHERE user_id = ? ORDER BY created_at DESC LIMIT 50',
        (request.user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    history = [{'id': r[0], 'endpoint': r[1], 'provider': r[2], 'tokens_used': r[3], 'created_at': r[4]} for r in rows]
    return jsonify({'contact_id': contact_id, 'history': history})


@app.route('/api/v1/contacts/bulk-import', methods=['POST'])
@api_key_required
def bulk_import_contacts():
    """Bulk import contacts from a JSON array."""
    data = request.get_json() or {}
    contacts_list = data.get('contacts', [])
    if not isinstance(contacts_list, list):
        return jsonify({'error': 'contacts must be a JSON array'}), 400
    if len(contacts_list) > 1000:
        return jsonify({'error': 'Maximum 1000 contacts per import'}), 400
    log_api_usage(request.user_id, 'contacts/bulk-import')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    imported = 0
    errors = []
    for i, c in enumerate(contacts_list):
        if not isinstance(c, dict):
            errors.append({'index': i, 'error': 'must be an object'})
            continue
        try:
            cursor.execute(
                'INSERT INTO contacts (user_id, email, phone, name, company, source) VALUES (?, ?, ?, ?, ?, ?)',
                (request.user_id, c.get('email'), c.get('phone'), c.get('name'), c.get('company'), c.get('source', 'bulk-import'))
            )
            imported += 1
        except Exception as e:
            errors.append({'index': i, 'error': str(e)})
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'imported': imported, 'errors': errors})


@app.route('/api/v1/contacts/export', methods=['GET'])
@api_key_required
def export_contacts():
    """Export all contacts as JSON."""
    log_api_usage(request.user_id, 'contacts/export')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM contacts WHERE user_id = ? ORDER BY created_at DESC', (request.user_id,))
    columns = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    contacts = []
    for row in rows:
        c = dict(zip(columns, row))
        if c.get('enriched_data'):
            try:
                c['enriched_data'] = json.loads(c['enriched_data'])
            except Exception:
                pass
        contacts.append(c)
    return jsonify({'status': 'ok', 'count': len(contacts), 'contacts': contacts})


@app.route('/api/v1/contacts/search', methods=['POST'])
@api_key_required
def search_contacts():
    """Advanced contact search with filters."""
    data = request.get_json() or {}
    log_api_usage(request.user_id, 'contacts/search')
    query = data.get('query', '')
    source = data.get('source')
    limit = min(int(data.get('limit', 50)), 200)
    offset = int(data.get('offset', 0))
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    where = ['user_id = ?']
    params = [request.user_id]
    if query:
        where.append('(name LIKE ? OR email LIKE ? OR phone LIKE ? OR company LIKE ?)')
        like = f'%{query}%'
        params.extend([like, like, like, like])
    if source:
        where.append('source = ?')
        params.append(source)
    sql = f'SELECT * FROM contacts WHERE {" AND ".join(where)} ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    cursor.execute(sql, params)
    columns = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    contacts = [dict(zip(columns, r)) for r in rows]
    return jsonify({'status': 'ok', 'count': len(contacts), 'contacts': contacts})


@app.route('/api/v1/contacts/stats', methods=['GET'])
@api_key_required
def contacts_stats():
    """Count stats by source and date."""
    log_api_usage(request.user_id, 'contacts/stats')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM contacts WHERE user_id = ?', (request.user_id,))
    total = cursor.fetchone()[0]
    cursor.execute(
        'SELECT source, COUNT(*) as count FROM contacts WHERE user_id = ? GROUP BY source ORDER BY count DESC',
        (request.user_id,)
    )
    by_source = [{'source': r[0], 'count': r[1]} for r in cursor.fetchall()]
    cursor.execute(
        "SELECT date(created_at) as day, COUNT(*) as count FROM contacts WHERE user_id = ? GROUP BY day ORDER BY day DESC LIMIT 30",
        (request.user_id,)
    )
    by_date = [{'date': r[0], 'count': r[1]} for r in cursor.fetchall()]
    conn.close()
    return jsonify({'status': 'ok', 'total': total, 'by_source': by_source, 'by_date': by_date})


@app.route('/api/v1/contacts/bulk-delete', methods=['DELETE'])
@api_key_required
def bulk_delete_contacts():
    """Bulk delete contacts by list of IDs."""
    data = request.get_json() or {}
    ids = data.get('ids', [])
    if not isinstance(ids, list) or not ids:
        return jsonify({'error': 'ids must be a non-empty array'}), 400
    log_api_usage(request.user_id, 'contacts/bulk-delete')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(ids))
    params = [request.user_id] + list(ids)
    cursor.execute(f'DELETE FROM contacts WHERE user_id = ? AND id IN ({placeholders})', params)
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'deleted': deleted})


# ═══════════════════════════════════════════════════════════
# CALLER ID — 6 endpoints
# ═══════════════════════════════════════════════════════════

@app.route('/api/v1/callerid/identify', methods=['POST'])
@api_key_required
def callerid_identify():
    """Identify a phone number or email."""
    data = request.get_json() or {}
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip()
    log_api_usage(request.user_id, 'callerid/identify')
    result = {}
    if email:
        from providers import MailcheckAPI
        result = MailcheckAPI.validate(email)
        result['input_type'] = 'email'
    elif phone:
        clean_phone = ''.join(filter(str.isdigit, phone))
        result = {
            'input_type': 'phone',
            'phone': phone,
            'clean_phone': clean_phone,
            'length': len(clean_phone),
            'note': 'Basic phone validation only. Use OSINT for deep lookup.',
        }
    else:
        return jsonify({'error': 'phone or email required'}), 400
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO caller_logs (user_id, phone, result, spam_score) VALUES (?, ?, ?, ?)',
        (request.user_id, phone or email, json.dumps(result), 0.0)
    )
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'log_id': log_id, 'result': result})


@app.route('/api/v1/callerid/history', methods=['GET'])
@api_key_required
def callerid_history():
    """List caller logs for the current user."""
    log_api_usage(request.user_id, 'callerid/history')
    limit = min(int(request.args.get('limit', 50)), 200)
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, phone, result, spam_score, carrier, location, created_at FROM caller_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
        (request.user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    logs = []
    for r in rows:
        entry = {'id': r[0], 'phone': r[1], 'spam_score': r[3], 'carrier': r[4], 'location': r[5], 'created_at': r[6]}
        try:
            entry['result'] = json.loads(r[2]) if r[2] else {}
        except Exception:
            entry['result'] = {}
        logs.append(entry)
    return jsonify({'status': 'ok', 'count': len(logs), 'logs': logs})


@app.route('/api/v1/callerid/report-spam', methods=['POST'])
@api_key_required
def callerid_report_spam():
    """Report a phone number as spam."""
    data = request.get_json() or {}
    phone = data.get('phone', '').strip()
    if not phone:
        return jsonify({'error': 'phone is required'}), 400
    log_api_usage(request.user_id, 'callerid/report-spam')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO caller_logs (user_id, phone, result, spam_score) VALUES (?, ?, ?, ?)',
        (request.user_id, phone, json.dumps({'spam': True, 'reported_by': request.user_id}), 1.0)
    )
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'reported', 'log_id': log_id, 'phone': phone})


@app.route('/api/v1/callerid/spam-list', methods=['GET'])
@api_key_required
def callerid_spam_list():
    """List phones reported as spam by current user."""
    log_api_usage(request.user_id, 'callerid/spam-list')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, phone, created_at FROM caller_logs WHERE user_id = ? AND spam_score >= 1.0 ORDER BY created_at DESC',
        (request.user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    spam = [{'id': r[0], 'phone': r[1], 'created_at': r[2]} for r in rows]
    return jsonify({'status': 'ok', 'count': len(spam), 'spam': spam})


@app.route('/api/v1/callerid/history/<int:log_id>', methods=['DELETE'])
@api_key_required
def delete_callerid_history(log_id):
    """Delete a caller log entry."""
    log_api_usage(request.user_id, 'callerid/history/delete')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM caller_logs WHERE id = ? AND user_id = ?', (log_id, request.user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Log entry not found'}), 404
    cursor.execute('DELETE FROM caller_logs WHERE id = ? AND user_id = ?', (log_id, request.user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'deleted', 'id': log_id})


@app.route('/api/v1/callerid/stats', methods=['GET'])
@api_key_required
def callerid_stats():
    """Stats on caller logs."""
    log_api_usage(request.user_id, 'callerid/stats')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM caller_logs WHERE user_id = ?', (request.user_id,))
    total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM caller_logs WHERE user_id = ? AND spam_score >= 1.0', (request.user_id,))
    spam_total = cursor.fetchone()[0]
    cursor.execute(
        "SELECT date(created_at) as day, COUNT(*) as count FROM caller_logs WHERE user_id = ? GROUP BY day ORDER BY day DESC LIMIT 7",
        (request.user_id,)
    )
    by_date = [{'date': r[0], 'count': r[1]} for r in cursor.fetchall()]
    conn.close()
    return jsonify({'status': 'ok', 'total': total, 'spam_total': spam_total, 'by_date': by_date})


# ═══════════════════════════════════════════════════════════
# OSINT — 10 endpoints
# ═══════════════════════════════════════════════════════════

def _check_osint_tier():
    """Return 403 response if user is on free tier, else None."""
    if getattr(request, 'user_tier', 'free') == 'free':
        return jsonify({'error': 'OSINT features require pro or enterprise tier'}), 403
    return None


@app.route('/api/v1/osint/investigate', methods=['POST'])
@api_key_required
def osint_investigate():
    """Full OSINT investigation (pro/enterprise only)."""
    err = _check_osint_tier()
    if err:
        return err
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    query_type = data.get('type', 'email').strip()
    if not query:
        return jsonify({'error': 'query is required'}), 400
    log_api_usage(request.user_id, 'osint/investigate')
    result = osint_engine.full_investigation(query, query_type)
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    tools_used = list(result.get('tools', {}).keys())
    cursor.execute(
        'INSERT INTO osint_investigations (user_id, query, query_type, results, tools_used) VALUES (?, ?, ?, ?, ?)',
        (request.user_id, query, query_type, json.dumps(result), json.dumps(tools_used))
    )
    inv_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'id': inv_id, 'result': result})


@app.route('/api/v1/osint/email', methods=['POST'])
@api_key_required
def osint_email():
    """Email OSINT (pro/enterprise only)."""
    err = _check_osint_tier()
    if err:
        return err
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    if not email:
        return jsonify({'error': 'email is required'}), 400
    log_api_usage(request.user_id, 'osint/email')
    result = osint_engine.investigate_email(email)
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO osint_investigations (user_id, query, query_type, results, tools_used) VALUES (?, ?, ?, ?, ?)',
        (request.user_id, email, 'email', json.dumps(result), json.dumps(['theharvester', 'holehe']))
    )
    inv_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'id': inv_id, 'result': result})


@app.route('/api/v1/osint/username', methods=['POST'])
@api_key_required
def osint_username():
    """Username OSINT (pro/enterprise only)."""
    err = _check_osint_tier()
    if err:
        return err
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    if not username:
        return jsonify({'error': 'username is required'}), 400
    log_api_usage(request.user_id, 'osint/username')
    result = osint_engine.investigate_username(username)
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO osint_investigations (user_id, query, query_type, results, tools_used) VALUES (?, ?, ?, ?, ?)',
        (request.user_id, username, 'username', json.dumps(result), json.dumps(['sherlock']))
    )
    inv_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'id': inv_id, 'result': result})


@app.route('/api/v1/osint/phone', methods=['POST'])
@api_key_required
def osint_phone():
    """Phone OSINT (pro/enterprise only)."""
    err = _check_osint_tier()
    if err:
        return err
    data = request.get_json() or {}
    phone = data.get('phone', '').strip()
    if not phone:
        return jsonify({'error': 'phone is required'}), 400
    log_api_usage(request.user_id, 'osint/phone')
    result = osint_engine.investigate_phone(phone)
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO osint_investigations (user_id, query, query_type, results, tools_used) VALUES (?, ?, ?, ?, ?)',
        (request.user_id, phone, 'phone', json.dumps(result), json.dumps(['phoneinfoga']))
    )
    inv_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'id': inv_id, 'result': result})


@app.route('/api/v1/osint/domain', methods=['POST'])
@api_key_required
def osint_domain():
    """Domain OSINT (pro/enterprise only)."""
    err = _check_osint_tier()
    if err:
        return err
    data = request.get_json() or {}
    domain = data.get('domain', '').strip()
    if not domain:
        return jsonify({'error': 'domain is required'}), 400
    log_api_usage(request.user_id, 'osint/domain')
    result = osint_engine.investigate_domain(domain)
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO osint_investigations (user_id, query, query_type, results, tools_used) VALUES (?, ?, ?, ?, ?)',
        (request.user_id, domain, 'domain', json.dumps(result), json.dumps(['subfinder', 'theharvester']))
    )
    inv_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'id': inv_id, 'result': result})


@app.route('/api/v1/osint/history', methods=['GET'])
@api_key_required
def osint_history():
    """List all OSINT investigations for the current user."""
    log_api_usage(request.user_id, 'osint/history')
    limit = min(int(request.args.get('limit', 20)), 100)
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, query, query_type, tools_used, created_at FROM osint_investigations WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
        (request.user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    investigations = []
    for r in rows:
        entry = {'id': r[0], 'query': r[1], 'type': r[2], 'created_at': r[4]}
        try:
            entry['tools_used'] = json.loads(r[3]) if r[3] else []
        except Exception:
            entry['tools_used'] = []
        investigations.append(entry)
    return jsonify({'status': 'ok', 'count': len(investigations), 'investigations': investigations})


@app.route('/api/v1/osint/history/<int:inv_id>', methods=['GET'])
@api_key_required
def osint_history_detail(inv_id):
    """Get a single OSINT investigation."""
    log_api_usage(request.user_id, 'osint/history/detail')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, query, query_type, results, tools_used, created_at FROM osint_investigations WHERE id = ? AND user_id = ?',
        (inv_id, request.user_id)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Investigation not found'}), 404
    result = {'id': row[0], 'query': row[1], 'type': row[2], 'created_at': row[5]}
    try:
        result['results'] = json.loads(row[3]) if row[3] else {}
    except Exception:
        result['results'] = {}
    try:
        result['tools_used'] = json.loads(row[4]) if row[4] else []
    except Exception:
        result['tools_used'] = []
    return jsonify({'status': 'ok', 'investigation': result})


@app.route('/api/v1/osint/history/<int:inv_id>', methods=['DELETE'])
@api_key_required
def osint_history_delete(inv_id):
    """Delete an OSINT investigation."""
    log_api_usage(request.user_id, 'osint/history/delete')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM osint_investigations WHERE id = ? AND user_id = ?', (inv_id, request.user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Investigation not found'}), 404
    cursor.execute('DELETE FROM osint_investigations WHERE id = ? AND user_id = ?', (inv_id, request.user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'deleted', 'id': inv_id})


@app.route('/api/v1/osint/stats', methods=['GET'])
@api_key_required
def osint_stats():
    """OSINT investigation stats."""
    log_api_usage(request.user_id, 'osint/stats')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM osint_investigations WHERE user_id = ?', (request.user_id,))
    total = cursor.fetchone()[0]
    cursor.execute(
        'SELECT query_type, COUNT(*) as count FROM osint_investigations WHERE user_id = ? GROUP BY query_type ORDER BY count DESC',
        (request.user_id,)
    )
    by_type = [{'type': r[0], 'count': r[1]} for r in cursor.fetchall()]
    cursor.execute(
        "SELECT date(created_at) as day, COUNT(*) as count FROM osint_investigations WHERE user_id = ? GROUP BY day ORDER BY day DESC LIMIT 7",
        (request.user_id,)
    )
    by_date = [{'date': r[0], 'count': r[1]} for r in cursor.fetchall()]
    conn.close()
    return jsonify({'status': 'ok', 'total': total, 'by_type': by_type, 'by_date': by_date})


@app.route('/api/v1/osint/batch', methods=['POST'])
@api_key_required
def osint_batch():
    """Batch OSINT investigations (up to 5 queries, pro/enterprise only)."""
    err = _check_osint_tier()
    if err:
        return err
    data = request.get_json() or {}
    queries = data.get('queries', [])
    if not isinstance(queries, list) or not queries:
        return jsonify({'error': 'queries must be a non-empty array'}), 400
    if len(queries) > 5:
        return jsonify({'error': 'Maximum 5 queries per batch'}), 400
    log_api_usage(request.user_id, 'osint/batch')
    results = []
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    for q in queries:
        if not isinstance(q, dict):
            results.append({'error': 'each query must be {type, value}'})
            continue
        qtype = q.get('type', 'email')
        qvalue = q.get('value', '').strip()
        if not qvalue:
            results.append({'error': 'value is required', 'query': q})
            continue
        inv_result = osint_engine.full_investigation(qvalue, qtype)
        tools_used = list(inv_result.get('tools', {}).keys())
        cursor.execute(
            'INSERT INTO osint_investigations (user_id, query, query_type, results, tools_used) VALUES (?, ?, ?, ?, ?)',
            (request.user_id, qvalue, qtype, json.dumps(inv_result), json.dumps(tools_used))
        )
        inv_id = cursor.lastrowid
        results.append({'id': inv_id, 'query': qvalue, 'type': qtype, 'result': inv_result})
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'count': len(results), 'results': results})


# ═══════════════════════════════════════════════════════════
# QR CARDS — 8 endpoints
# ═══════════════════════════════════════════════════════════

import qrcode
import io
import base64


def _generate_qr_b64(data_str):
    """Generate a QR code from a string and return base64 PNG."""
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(data_str)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')
    except Exception as e:
        return None


@app.route('/api/v1/qrcards', methods=['POST'])
@api_key_required
def create_qrcard():
    """Create a new QR card."""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    log_api_usage(request.user_id, 'qrcards/create')
    card_data = {
        'name': name,
        'title': data.get('title'),
        'company': data.get('company'),
        'email': data.get('email'),
        'phone': data.get('phone'),
        'website': data.get('website'),
        'custom': data.get('custom', {}),
    }
    vcard_str = f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\n"
    if data.get('email'):
        vcard_str += f"EMAIL:{data['email']}\n"
    if data.get('phone'):
        vcard_str += f"TEL:{data['phone']}\n"
    if data.get('company'):
        vcard_str += f"ORG:{data['company']}\n"
    if data.get('website'):
        vcard_str += f"URL:{data['website']}\n"
    vcard_str += "END:VCARD"
    qr_b64 = _generate_qr_b64(vcard_str)
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO qr_cards (user_id, name, title, company, email, phone, website, card_data, qr_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (request.user_id, name, data.get('title'), data.get('company'), data.get('email'),
         data.get('phone'), data.get('website'), json.dumps(card_data), qr_b64)
    )
    card_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'created', 'id': card_id, 'qr_code': qr_b64})


@app.route('/api/v1/qrcards', methods=['GET'])
@api_key_required
def list_qrcards():
    """List all QR cards for the current user."""
    log_api_usage(request.user_id, 'qrcards/list')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, title, company, email, phone, website, created_at FROM qr_cards WHERE user_id = ? ORDER BY created_at DESC',
        (request.user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    cards = [
        {'id': r[0], 'name': r[1], 'title': r[2], 'company': r[3], 'email': r[4], 'phone': r[5], 'website': r[6], 'created_at': r[7]}
        for r in rows
    ]
    return jsonify({'status': 'ok', 'count': len(cards), 'cards': cards})


@app.route('/api/v1/qrcards/<int:card_id>', methods=['GET'])
@api_key_required
def get_qrcard(card_id):
    """Get a single QR card."""
    log_api_usage(request.user_id, 'qrcards/get')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, title, company, email, phone, website, card_data, qr_code, created_at FROM qr_cards WHERE id = ? AND user_id = ?',
        (card_id, request.user_id)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Card not found'}), 404
    card = {'id': row[0], 'name': row[1], 'title': row[2], 'company': row[3], 'email': row[4],
            'phone': row[5], 'website': row[6], 'created_at': row[9]}
    try:
        card['card_data'] = json.loads(row[7]) if row[7] else {}
    except Exception:
        card['card_data'] = {}
    card['qr_code'] = row[8]
    return jsonify({'status': 'ok', 'card': card})


@app.route('/api/v1/qrcards/<int:card_id>', methods=['PUT'])
@api_key_required
def update_qrcard(card_id):
    """Update a QR card."""
    data = request.get_json() or {}
    log_api_usage(request.user_id, 'qrcards/update')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM qr_cards WHERE id = ? AND user_id = ?', (card_id, request.user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Card not found'}), 404
    fields = []
    values = []
    for field in ['name', 'title', 'company', 'email', 'phone', 'website']:
        if field in data:
            fields.append(f'{field} = ?')
            values.append(data[field])
    if fields:
        # Regenerate QR if contact fields changed
        cursor.execute('SELECT name, title, company, email, phone, website FROM qr_cards WHERE id = ?', (card_id,))
        existing = cursor.fetchone()
        merged = {
            'name': data.get('name', existing[0]),
            'email': data.get('email', existing[3]),
            'phone': data.get('phone', existing[4]),
            'company': data.get('company', existing[2]),
            'website': data.get('website', existing[5]),
        }
        vcard_str = f"BEGIN:VCARD\nVERSION:3.0\nFN:{merged['name']}\n"
        if merged.get('email'):
            vcard_str += f"EMAIL:{merged['email']}\n"
        if merged.get('phone'):
            vcard_str += f"TEL:{merged['phone']}\n"
        if merged.get('company'):
            vcard_str += f"ORG:{merged['company']}\n"
        if merged.get('website'):
            vcard_str += f"URL:{merged['website']}\n"
        vcard_str += "END:VCARD"
        qr_b64 = _generate_qr_b64(vcard_str)
        if qr_b64:
            fields.append('qr_code = ?')
            values.append(qr_b64)
        card_data_val = json.dumps(merged)
        fields.append('card_data = ?')
        values.append(card_data_val)
        values.extend([card_id, request.user_id])
        cursor.execute(f'UPDATE qr_cards SET {", ".join(fields)} WHERE id = ? AND user_id = ?', values)
        conn.commit()
    conn.close()
    return jsonify({'status': 'updated', 'id': card_id})


@app.route('/api/v1/qrcards/<int:card_id>', methods=['DELETE'])
@api_key_required
def delete_qrcard(card_id):
    """Delete a QR card."""
    log_api_usage(request.user_id, 'qrcards/delete')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM qr_cards WHERE id = ? AND user_id = ?', (card_id, request.user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Card not found'}), 404
    cursor.execute('DELETE FROM qr_cards WHERE id = ? AND user_id = ?', (card_id, request.user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'deleted', 'id': card_id})


@app.route('/api/v1/qrcards/<int:card_id>/qr', methods=['GET'])
@api_key_required
def get_qrcard_qr(card_id):
    """Return QR code as base64 PNG."""
    log_api_usage(request.user_id, 'qrcards/qr')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT qr_code FROM qr_cards WHERE id = ? AND user_id = ?', (card_id, request.user_id))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Card not found'}), 404
    return jsonify({'status': 'ok', 'card_id': card_id, 'qr_code': row[0], 'format': 'base64_png'})


@app.route('/api/v1/qrcards/scan', methods=['POST'])
@api_key_required
def scan_qrcard():
    """Decode a QR code from a base64 image."""
    data = request.get_json() or {}
    image_b64 = data.get('image')
    if not image_b64:
        return jsonify({'error': 'image (base64) is required'}), 400
    log_api_usage(request.user_id, 'qrcards/scan')
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
        from PIL import Image
        img_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_bytes))
        decoded = pyzbar_decode(img)
        if decoded:
            qr_data = decoded[0].data.decode('utf-8')
            return jsonify({'status': 'ok', 'data': qr_data})
        else:
            return jsonify({'status': 'no_qr_found', 'data': None})
    except ImportError:
        return jsonify({'status': 'not_supported', 'error': 'pyzbar not installed. Install: pip install pyzbar'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400


@app.route('/api/v1/qrcards/public/<int:card_id>', methods=['GET'])
def get_public_qrcard(card_id):
    """Public endpoint — no auth required. Returns public card data."""
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, title, company, email, phone, website, qr_code, created_at FROM qr_cards WHERE id = ?',
        (card_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Card not found'}), 404
    card = {'id': row[0], 'name': row[1], 'title': row[2], 'company': row[3],
            'email': row[4], 'phone': row[5], 'website': row[6], 'qr_code': row[7], 'created_at': row[8]}
    return jsonify({'status': 'ok', 'card': card})


# ═══════════════════════════════════════════════════════════
# MONITORING — 7 endpoints
# ═══════════════════════════════════════════════════════════

@app.route('/api/v1/monitoring/alerts', methods=['POST'])
@api_key_required
def create_alert():
    """Create a new alert."""
    data = request.get_json() or {}
    alert_type = data.get('alert_type', '').strip()
    title = data.get('title', '').strip()
    if not alert_type or not title:
        return jsonify({'error': 'alert_type and title are required'}), 400
    log_api_usage(request.user_id, 'monitoring/alerts/create')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO alerts (user_id, contact_id, alert_type, title, message, severity) VALUES (?, ?, ?, ?, ?, ?)',
        (request.user_id, data.get('contact_id'), alert_type, title,
         data.get('message', ''), data.get('severity', 'info'))
    )
    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'created', 'id': alert_id})


@app.route('/api/v1/monitoring/alerts', methods=['GET'])
@api_key_required
def list_alerts():
    """List alerts, optionally filtered by read_status."""
    log_api_usage(request.user_id, 'monitoring/alerts/list')
    read_status = request.args.get('read_status')
    limit = min(int(request.args.get('limit', 50)), 200)
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    if read_status is not None:
        cursor.execute(
            'SELECT id, contact_id, alert_type, title, message, severity, read_status, created_at FROM alerts WHERE user_id = ? AND read_status = ? ORDER BY created_at DESC LIMIT ?',
            (request.user_id, 1 if read_status in ('true', '1') else 0, limit)
        )
    else:
        cursor.execute(
            'SELECT id, contact_id, alert_type, title, message, severity, read_status, created_at FROM alerts WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
            (request.user_id, limit)
        )
    rows = cursor.fetchall()
    conn.close()
    alerts = [
        {'id': r[0], 'contact_id': r[1], 'alert_type': r[2], 'title': r[3],
         'message': r[4], 'severity': r[5], 'read': bool(r[6]), 'created_at': r[7]}
        for r in rows
    ]
    return jsonify({'status': 'ok', 'count': len(alerts), 'alerts': alerts})


@app.route('/api/v1/monitoring/alerts/<int:alert_id>/read', methods=['PUT'])
@api_key_required
def mark_alert_read(alert_id):
    """Mark an alert as read."""
    log_api_usage(request.user_id, 'monitoring/alerts/read')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM alerts WHERE id = ? AND user_id = ?', (alert_id, request.user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Alert not found'}), 404
    cursor.execute('UPDATE alerts SET read_status = 1 WHERE id = ? AND user_id = ?', (alert_id, request.user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'updated', 'id': alert_id, 'read': True})


@app.route('/api/v1/monitoring/alerts/<int:alert_id>', methods=['DELETE'])
@api_key_required
def delete_alert(alert_id):
    """Delete an alert."""
    log_api_usage(request.user_id, 'monitoring/alerts/delete')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM alerts WHERE id = ? AND user_id = ?', (alert_id, request.user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Alert not found'}), 404
    cursor.execute('DELETE FROM alerts WHERE id = ? AND user_id = ?', (alert_id, request.user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'deleted', 'id': alert_id})


@app.route('/api/v1/monitoring/news', methods=['POST'])
@api_key_required
def monitoring_news():
    """Search news for a query using GoogleNewsRSS."""
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'query is required'}), 400
    log_api_usage(request.user_id, 'monitoring/news')
    from providers import GoogleNewsRSS
    result = GoogleNewsRSS.search(query, max_results=data.get('max_results', 10))
    return jsonify({'status': 'ok', 'result': result})


@app.route('/api/v1/monitoring/sanctions', methods=['GET'])
@api_key_required
def monitoring_sanctions():
    """Check a name or email against OpenSanctions."""
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify({'error': 'query parameter is required'}), 400
    log_api_usage(request.user_id, 'monitoring/sanctions')
    from providers import OpenSanctionsAPI
    result = OpenSanctionsAPI.check(query)
    return jsonify({'status': 'ok', 'query': query, 'result': result})


@app.route('/api/v1/monitoring/stats', methods=['GET'])
@api_key_required
def monitoring_stats():
    """Alert stats for the current user."""
    log_api_usage(request.user_id, 'monitoring/stats')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM alerts WHERE user_id = ?', (request.user_id,))
    total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM alerts WHERE user_id = ? AND read_status = 0', (request.user_id,))
    unread = cursor.fetchone()[0]
    cursor.execute(
        'SELECT severity, COUNT(*) as count FROM alerts WHERE user_id = ? GROUP BY severity ORDER BY count DESC',
        (request.user_id,)
    )
    by_severity = [{'severity': r[0], 'count': r[1]} for r in cursor.fetchall()]
    cursor.execute(
        "SELECT date(created_at) as day, COUNT(*) as count FROM alerts WHERE user_id = ? GROUP BY day ORDER BY day DESC LIMIT 7",
        (request.user_id,)
    )
    by_date = [{'date': r[0], 'count': r[1]} for r in cursor.fetchall()]
    conn.close()
    return jsonify({'status': 'ok', 'total': total, 'unread': unread, 'by_severity': by_severity, 'by_date': by_date})


# ═══════════════════════════════════════════════════════════
# AGENT TOOLS — 5 endpoints
# ═══════════════════════════════════════════════════════════

@app.route('/api/v1/agent/enrich', methods=['POST'])
@api_key_required
def agent_enrich():
    """Enrich contact data using the enrichment pipeline."""
    data = request.get_json() or {}
    if not data:
        return jsonify({'error': 'contact data is required'}), 400
    log_api_usage(request.user_id, 'agent/enrich')
    result = enrichment_pipeline.enrich_contact(data)
    return jsonify({'status': 'ok', 'result': result})


@app.route('/api/v1/agent/analyze', methods=['POST'])
@api_key_required
def agent_analyze():
    """Analyze contact completeness and data quality."""
    data = request.get_json() or {}
    log_api_usage(request.user_id, 'agent/analyze')
    fields_present = []
    fields_missing = []
    key_fields = ['email', 'phone', 'name', 'company', 'website', 'linkedin', 'twitter', 'location', 'title', 'bio']
    for f in key_fields:
        if data.get(f):
            fields_present.append(f)
        else:
            fields_missing.append(f)
    score = int(len(fields_present) / len(key_fields) * 100)
    quality_issues = []
    if data.get('email') and '@' not in data['email']:
        quality_issues.append({'field': 'email', 'issue': 'invalid format'})
    if data.get('phone'):
        clean = ''.join(filter(str.isdigit, data['phone']))
        if len(clean) < 7:
            quality_issues.append({'field': 'phone', 'issue': 'too short'})
    return jsonify({
        'status': 'ok',
        'completeness_score': score,
        'fields_present': fields_present,
        'fields_missing': fields_missing,
        'quality_issues': quality_issues,
        'recommendation': 'Use /agent/enrich to fill missing fields' if fields_missing else 'Contact looks complete',
    })


@app.route('/api/v1/agent/score', methods=['POST'])
@api_key_required
def agent_score():
    """Score one or multiple contacts by completeness (0-100)."""
    data = request.get_json() or {}
    log_api_usage(request.user_id, 'agent/score')
    contacts = data.get('contacts')
    if contacts is None:
        contacts = [data]
    key_fields = ['email', 'phone', 'name', 'company', 'website', 'linkedin', 'twitter', 'location', 'title', 'bio']
    scored = []
    for c in contacts:
        present = sum(1 for f in key_fields if c.get(f))
        score = int(present / len(key_fields) * 100)
        scored.append({'contact': c.get('email') or c.get('name') or 'unknown', 'score': score})
    return jsonify({'status': 'ok', 'scores': scored})


@app.route('/api/v1/agent/dedupe', methods=['POST'])
@api_key_required
def agent_dedupe():
    """Find duplicate contacts within the user's contact list (same email or phone)."""
    log_api_usage(request.user_id, 'agent/dedupe')
    conn = sqlite3.connect('contactiq.db')
    cursor = conn.cursor()
    # Find duplicate emails
    cursor.execute(
        '''SELECT email, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
           FROM contacts WHERE user_id = ? AND email IS NOT NULL AND email != ''
           GROUP BY email HAVING cnt > 1''',
        (request.user_id,)
    )
    email_dupes = [{'field': 'email', 'value': r[0], 'count': r[1], 'ids': r[2].split(',')} for r in cursor.fetchall()]
    # Find duplicate phones
    cursor.execute(
        '''SELECT phone, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
           FROM contacts WHERE user_id = ? AND phone IS NOT NULL AND phone != ''
           GROUP BY phone HAVING cnt > 1''',
        (request.user_id,)
    )
    phone_dupes = [{'field': 'phone', 'value': r[0], 'count': r[1], 'ids': r[2].split(',')} for r in cursor.fetchall()]
    conn.close()
    duplicates = email_dupes + phone_dupes
    return jsonify({'status': 'ok', 'duplicate_groups': len(duplicates), 'duplicates': duplicates})


@app.route('/api/v1/agent/status', methods=['GET'])
@api_key_required
def agent_status():
    """Return status of all 17 data providers."""
    log_api_usage(request.user_id, 'agent/status')
    from providers import ALL_PROVIDERS
    provider_status = []
    for name, info in ALL_PROVIDERS.items():
        provider_status.append({
            'name': name,
            'display_name': getattr(info['class'], 'display_name', name),
            'category': info.get('category', 'unknown'),
            'cost': info.get('cost', 'unknown'),
            'requires_key': info.get('key', False),
            'available': True,
        })
    return jsonify({
        'status': 'ok',
        'total_providers': len(provider_status),
        'providers': provider_status,
    })


if __name__ == '__main__':
    init_database()
    logger.info("ContactIQ Server starting...")
    logger.info("Backend features: 56 endpoints, 17 data sources, OSINT engine")
    app.run(debug=True, host='0.0.0.0', port=5000)
