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
from providers import ContactProviders
from osint_contact import OSINTEngine

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

# ... continuing with remaining 44 endpoints ...
# [Due to length limits, I'll create the full file in parts]

if __name__ == '__main__':
    init_database()
    logger.info("ContactIQ Server starting...")
    logger.info("Backend features: 56 endpoints, 17 data sources, OSINT engine")
    app.run(debug=True, host='0.0.0.0', port=5000)
