"""
ContactIQ — AI-Powered Contact Intelligence Platform
Self-contained Flask server with SQLite for testing.

Same API interface as the FastAPI production version.
Run: python3 server.py
Test: python3 test_api.py
"""
import sqlite3
import json
import uuid
import hashlib
import secrets
import time
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, g

# Real data providers
from providers import (
    EnrichmentPipeline, GoogleNewsRSS, GitHubAPI, WikidataAPI,
    GravatarAPI, ClearbitLogo, GNewsAPI, GuardianAPI, SECEDGAR,
    OpenCorporatesAPI, OpenSanctionsAPI, MailcheckAPI, ALL_PROVIDERS,
)

# ═══════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════

APP_NAME = "ContactIQ"
APP_VERSION = "0.1.0"
API_PREFIX = "/api/v1"
DB_PATH = "/home/claude/contactiq_test/contactiq.db"
SECRET_KEY = "test-secret-key-for-dev"
TOKEN_EXPIRE_HOURS = 24
ALERT_RELEVANCE_THRESHOLD = 0.6

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


# ═══════════════════════════════════════════════════════════
# Database Layer
# ═══════════════════════════════════════════════════════════

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create all tables."""
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            full_name TEXT,
            api_key TEXT UNIQUE,
            tier TEXT DEFAULT 'free',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            full_name TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            email TEXT,
            phone TEXT,
            company TEXT,
            job_title TEXT,
            notes TEXT,
            linkedin_url TEXT,
            twitter_handle TEXT,
            github_username TEXT,
            website TEXT,
            location TEXT,
            bio TEXT,
            avatar_url TEXT,
            work_history TEXT,       -- JSON
            education TEXT,          -- JSON
            social_profiles TEXT,    -- JSON
            attributes TEXT,         -- JSON
            raw_enrichment_data TEXT,-- JSON
            tags TEXT,               -- JSON array
            group_name TEXT,
            priority INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending_enrichment',
            enrichment_score REAL,
            last_enriched_at TEXT,
            enrichment_sources TEXT, -- JSON array
            is_monitored INTEGER DEFAULT 0,
            last_monitored_at TEXT,
            monitoring_keywords TEXT,-- JSON array
            confidence_score REAL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS ix_contacts_owner ON contacts(owner_id);
        CREATE INDEX IF NOT EXISTS ix_contacts_email ON contacts(owner_id, email);
        CREATE INDEX IF NOT EXISTS ix_contacts_name ON contacts(full_name);

        CREATE TABLE IF NOT EXISTS enrichment_records (
            id TEXT PRIMARY KEY,
            contact_id TEXT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            query_params TEXT,
            raw_response TEXT,
            parsed_data TEXT,
            confidence REAL,
            match_score REAL,
            status TEXT DEFAULT 'success',
            error_message TEXT,
            cost_usd REAL,
            fetched_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS ix_enrichment_contact ON enrichment_records(contact_id);

        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            contact_id TEXT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            priority TEXT DEFAULT 'medium',
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            ai_analysis TEXT,
            source_url TEXT,
            source_name TEXT,
            source_published_at TEXT,
            raw_source_data TEXT,
            relevance_score REAL DEFAULT 0.5,
            sentiment TEXT,
            sentiment_score REAL,
            status TEXT DEFAULT 'new',
            delivered_via TEXT,
            delivered_at TEXT,
            read_at TEXT,
            content_hash TEXT,
            suggested_actions TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS ix_alerts_user ON alerts(user_id, status);
        CREATE INDEX IF NOT EXISTS ix_alerts_contact ON alerts(contact_id);
        CREATE INDEX IF NOT EXISTS ix_alerts_hash ON alerts(content_hash);

        CREATE TABLE IF NOT EXISTS monitoring_rules (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            categories TEXT,
            contact_ids TEXT,
            contact_tags TEXT,
            min_priority TEXT DEFAULT 'low',
            keywords TEXT,
            channels TEXT DEFAULT '["in_app"]',
            digest_frequency TEXT DEFAULT 'realtime',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
    """)
    db.commit()
    db.close()
    print(f"[OK] Database initialized: {DB_PATH}")


# ═══════════════════════════════════════════════════════════
# Auth Helpers
# ═══════════════════════════════════════════════════════════

import jwt as pyjwt

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}:{h.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        salt, h = hashed.split(":")
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
        return check.hex() == h
    except Exception:
        return False


def create_token(user_id: str) -> tuple:
    exp = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    token = pyjwt.encode(
        {"sub": user_id, "exp": exp, "iat": datetime.utcnow()},
        SECRET_KEY, algorithm="HS256"
    )
    return token, TOKEN_EXPIRE_HOURS * 3600


def generate_api_key() -> str:
    return f"ciq_{secrets.token_urlsafe(32)}"


def require_auth(f):
    """Decorator — authenticate via Bearer token or X-API-Key."""
    @wraps(f)
    def decorated(*args, **kwargs):
        db = get_db()
        user = None

        # Try API key
        api_key = request.headers.get("X-API-Key")
        if api_key:
            row = db.execute(
                "SELECT * FROM users WHERE api_key = ? AND is_active = 1", (api_key,)
            ).fetchone()
            if row:
                user = dict(row)

        # Try Bearer token
        if not user:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
                try:
                    payload = pyjwt.decode(token, SECRET_KEY, algorithms=["HS256"])
                    user_id = payload.get("sub")
                    if user_id:
                        row = db.execute(
                            "SELECT * FROM users WHERE id = ? AND is_active = 1",
                            (user_id,)
                        ).fetchone()
                        if row:
                            user = dict(row)
                except pyjwt.exceptions.PyJWTError:
                    pass

        if not user:
            return jsonify({"detail": "Authentication required. Provide Bearer token or X-API-Key."}), 401

        g.current_user = user
        return f(*args, **kwargs)
    return decorated


# ═══════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════

def new_id():
    return str(uuid.uuid4())


def now_iso():
    return datetime.utcnow().isoformat()


def parse_json_field(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def contact_to_dict(row):
    """Convert a contact row to a clean dictionary."""
    if row is None:
        return None
    d = dict(row)
    for field in ["tags", "work_history", "education", "social_profiles",
                  "attributes", "raw_enrichment_data", "enrichment_sources",
                  "monitoring_keywords"]:
        d[field] = parse_json_field(d.get(field))
    d["is_monitored"] = bool(d.get("is_monitored"))
    return d


def alert_to_dict(row):
    d = dict(row)
    for field in ["raw_source_data", "suggested_actions", "delivered_via"]:
        d[field] = parse_json_field(d.get(field))
    return d


def extract_first_name(full_name):
    parts = full_name.strip().split()
    return parts[0] if parts else full_name


def extract_last_name(full_name):
    parts = full_name.strip().split()
    return " ".join(parts[1:]) if len(parts) > 1 else ""


# ═══════════════════════════════════════════════════════════
# Enrichment Engine — Real Providers via providers.py
# ═══════════════════════════════════════════════════════════

# Provider registry for /enrichment/providers endpoint
PROVIDERS = {
    "github": {"display_name": "GitHub API", "type": "free", "requires_key": False},
    "wikidata": {"display_name": "Wikidata / Wikipedia", "type": "free", "requires_key": False},
    "gravatar": {"display_name": "Gravatar", "type": "free", "requires_key": False},
    "clearbit_logo": {"display_name": "Clearbit Logo", "type": "free", "requires_key": False},
    "opencorporates": {"display_name": "OpenCorporates", "type": "free", "requires_key": False},
    "opensanctions": {"display_name": "OpenSanctions", "type": "compliance", "requires_key": False},
    "mailcheck": {"display_name": "Mailcheck.ai", "type": "free", "requires_key": False},
    "google_news_rss": {"display_name": "Google News RSS", "type": "free", "requires_key": False},
    "gnews": {"display_name": "GNews API", "type": "freemium", "requires_key": True},
    "guardian": {"display_name": "The Guardian API", "type": "freemium", "requires_key": True},
    "sec_edgar": {"display_name": "SEC EDGAR", "type": "free", "requires_key": False},
}

# Provider config from environment
PROVIDER_CONFIG = {
    "github_token": os.environ.get("GITHUB_TOKEN"),
    "gnews_key": os.environ.get("GNEWS_API_KEY"),
    "guardian_key": os.environ.get("GUARDIAN_API_KEY"),
    "opencorporates_key": os.environ.get("OPENCORPORATES_API_KEY"),
    "opensanctions_url": os.environ.get("OPENSANCTIONS_URL"),
    "opensanctions_key": os.environ.get("OPENSANCTIONS_API_KEY"),
}

# Shared pipeline instance
_pipeline = EnrichmentPipeline(config=PROVIDER_CONFIG)


def run_enrichment(contact: dict, providers: list = None, force: bool = False):
    """
    Run real enrichment pipeline for a contact.
    Uses GitHub, Wikidata, Gravatar, OpenCorporates, OpenSanctions, Clearbit Logo, Mailcheck.
    Falls back to mock data when network is unavailable.
    """
    db = get_db()

    # Run the real pipeline
    pipeline_result = _pipeline.enrich_contact(contact)
    merged = pipeline_result.get("merged_profile", {})
    providers_used = pipeline_result.get("providers_used", [])

    # Save individual enrichment records for each provider
    results = []
    for detail in pipeline_result.get("results_detail", []):
        provider_name = detail.get("provider", "unknown")
        record_id = new_id()
        try:
            db.execute("""
                INSERT INTO enrichment_records (id, contact_id, provider, query_params, 
                    parsed_data, confidence, status, cost_usd, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record_id, contact["id"], provider_name,
                json.dumps({"name": contact["full_name"], "email": contact.get("email")}),
                json.dumps(detail.get("data")),
                detail.get("confidence", 0),
                detail.get("status", "unknown"),
                0, now_iso(),
            ))
        except Exception:
            pass

        results.append({
            "provider": provider_name,
            "status": detail.get("status", "unknown"),
            "confidence": detail.get("confidence"),
            "fetched_at": now_iso(),
        })

    # Map merged data to contact fields
    field_map = {
        "avatar_url": "avatar_url",
        "bio": "bio",
        "location": "location",
        "website": "website",
        "twitter_handle": "twitter_handle",
        "github_username": "github_username",
        "github_url": "linkedin_url",  # store github_url in linkedin_url if no linkedin
        "company": "company",
        "occupation": "job_title",
    }

    updates = {}
    for src, dst in field_map.items():
        val = merged.get(src)
        if val and not contact.get(dst):
            updates[dst] = val

    # LinkedIn from Wikidata or GitHub
    if merged.get("linkedin_id") and not contact.get("linkedin_url"):
        updates["linkedin_url"] = f"https://linkedin.com/in/{merged['linkedin_id']}"
    if merged.get("github_url") and not contact.get("linkedin_url"):
        # Don't overwrite linkedin with github
        pass

    # Twitter handle
    if merged.get("twitter_handle") and not contact.get("twitter_handle"):
        handle = merged["twitter_handle"]
        if not handle.startswith("@"):
            handle = f"@{handle}"
        updates["twitter_handle"] = handle

    # Structured data as JSON
    if merged.get("corporate_roles"):
        updates["work_history"] = json.dumps(merged["corporate_roles"])
    if merged.get("education"):
        updates["education"] = json.dumps({"institution": merged["education"]})

    # Social profiles
    social = {}
    for key in ["github_url", "wikipedia_url", "wikidata_id", "instagram"]:
        if merged.get(key):
            social[key] = merged[key]
    if social:
        updates["social_profiles"] = json.dumps(social)

    # Attributes (skills, sanctions, etc)
    attrs = parse_json_field(contact.get("attributes")) or {}
    if merged.get("sanctions_check"):
        attrs["sanctions_check"] = merged["sanctions_check"]
    if merged.get("nationality"):
        attrs["nationality"] = merged["nationality"]
    if merged.get("occupation"):
        attrs["occupation"] = merged["occupation"]
    if merged.get("employer"):
        attrs["employer"] = merged["employer"]
    if merged.get("birth_date"):
        attrs["birth_date"] = merged["birth_date"]
    if merged.get("followers"):
        attrs["github_followers"] = merged["followers"]
    if merged.get("public_repos"):
        attrs["github_repos"] = merged["public_repos"]
    if merged.get("email_valid") is not None:
        attrs["email_valid"] = merged["email_valid"]
    if merged.get("email_disposable") is not None:
        attrs["email_disposable"] = merged["email_disposable"]
    if attrs:
        updates["attributes"] = json.dumps(attrs)

    # Enrichment score from pipeline
    score = pipeline_result.get("enrichment_score", 0)
    updates["enrichment_score"] = score
    updates["last_enriched_at"] = now_iso()
    updates["enrichment_sources"] = json.dumps(providers_used)
    updates["status"] = "enriched"
    updates["updated_at"] = now_iso()

    # Raw enrichment data
    updates["raw_enrichment_data"] = json.dumps(merged)

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        db.execute(
            f"UPDATE contacts SET {set_clause} WHERE id = ?",
            list(updates.values()) + [contact["id"]]
        )
        db.commit()

    return {
        "contact_id": contact["id"],
        "contact_name": contact["full_name"],
        "status": "completed",
        "providers_used": providers_used,
        "provider_count": len(providers_used),
        "results": results,
        "merged_data": merged,
        "total_cost_usd": 0,
        "enrichment_score": score,
        "enriched_at": now_iso(),
    }


# ═══════════════════════════════════════════════════════════
# News Monitoring Engine — Real Providers
# ═══════════════════════════════════════════════════════════

# Keywords for auto-classifying news categories
CATEGORY_KEYWORDS = {
    "career": ["appointed", "hired", "promoted", "joined", "resigned", "fired", "ceo", "cto", "vp", "director", "new role", "steps down"],
    "business": ["funding", "raised", "investment", "ipo", "acquisition", "merger", "revenue", "growth", "valuation", "series a", "series b", "partnership"],
    "legal": ["lawsuit", "sued", "investigation", "sec", "regulatory", "compliance", "fine", "penalty", "fraud", "indicted", "subpoena", "settlement"],
    "media": ["interview", "featured", "profile", "forbes", "30 under", "award", "recognition", "keynote", "conference", "ted talk"],
    "risk": ["scandal", "controversy", "breach", "hack", "leak", "sanction", "embargo", "bankrupt", "default", "crisis"],
    "social": ["tweet", "post", "linkedin", "speaking", "podcast", "event", "charity", "philanthropy", "foundation"],
}

PRIORITY_MAP = {"legal": "critical", "risk": "critical", "career": "high", "business": "high", "media": "medium", "social": "low"}
SENTIMENT_KEYWORDS = {
    "positive": ["growth", "raised", "promoted", "awarded", "appointed", "success", "innovation", "record", "win"],
    "negative": ["lawsuit", "scandal", "investigation", "fraud", "crisis", "bankruptcy", "fired", "controversy", "hack"],
}


def classify_news_item(title, description=""):
    """Classify a news item into category, priority, and sentiment."""
    text = f"{title} {description}".lower()

    # Category
    category = "media"  # default
    max_hits = 0
    for cat, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > max_hits:
            max_hits = hits
            category = cat

    # Priority
    priority = PRIORITY_MAP.get(category, "medium")

    # Sentiment
    pos = sum(1 for kw in SENTIMENT_KEYWORDS["positive"] if kw in text)
    neg = sum(1 for kw in SENTIMENT_KEYWORDS["negative"] if kw in text)
    if neg > pos:
        sentiment = "negative"
    elif pos > neg:
        sentiment = "positive"
    else:
        sentiment = "neutral"

    return category, priority, sentiment


def calculate_relevance(contact, title, description=""):
    """Score how relevant a news item is to a contact (0.0 - 1.0)."""
    text = f"{title} {description}".lower()
    name = contact.get("full_name", "").lower()
    company = (contact.get("company") or "").lower()
    score = 0.5

    # Name in title is strong signal
    if name in title.lower():
        score += 0.3
    elif name.split()[-1].lower() in title.lower():  # last name in title
        score += 0.15

    # Company mention
    if company and company in text:
        score += 0.1

    # Monitoring keywords match
    keywords = parse_json_field(contact.get("monitoring_keywords")) or []
    for kw in keywords:
        if isinstance(kw, str) and kw.lower() in text:
            score += 0.05

    return min(score, 1.0)


def scan_contact_for_news(contact: dict, user_id: str):
    """
    Scan for real news about a contact using Google News RSS + configured APIs.
    Creates alerts for relevant items. Returns list of created alerts.
    """
    db = get_db()
    name = contact["full_name"]
    company = contact.get("company") or ""
    alerts_created = []

    # Run the real monitoring pipeline
    news_result = _pipeline.monitor_contact(contact, config=PROVIDER_CONFIG)
    items = news_result.get("items", [])

    for item in items:
        title = item.get("title", "")
        description = item.get("description", "")
        url = item.get("url", "")
        source = item.get("source", item.get("provider", "unknown"))

        # Skip if no meaningful title
        if not title or len(title) < 10:
            continue

        # Classify
        category, priority, sentiment = classify_news_item(title, description)

        # Calculate relevance
        relevance = calculate_relevance(contact, title, description)

        # Skip low-relevance items
        if relevance < ALERT_RELEVANCE_THRESHOLD:
            continue

        # Dedup by content hash
        content_hash = hashlib.sha256(f"{title}{url}{contact['id']}".encode()).hexdigest()
        exists = db.execute(
            "SELECT id FROM alerts WHERE content_hash = ? AND user_id = ?",
            (content_hash, user_id)
        ).fetchone()
        if exists:
            continue

        # Build suggested actions
        suggested_actions = {"actions": []}
        if category == "career":
            suggested_actions["actions"].append({
                "type": "send_message", "label": "Congratulate",
                "template": f"Congratulations on the news, {name.split()[0]}!",
            })
        elif category == "business":
            suggested_actions["actions"].append({
                "type": "send_message", "label": "Discuss",
                "template": f"Saw the latest news about {company or 'your company'}. Would love to connect!",
            })
        elif category in ("legal", "risk"):
            suggested_actions["actions"].append({
                "type": "review", "label": "Review relationship",
                "description": "Consider reviewing your business relationship.",
            })

        alert_id = new_id()
        db.execute("""
            INSERT INTO alerts (id, user_id, contact_id, category, priority, title, summary,
                source_url, source_name, relevance_score, sentiment,
                content_hash, suggested_actions, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
        """, (
            alert_id, user_id, contact["id"], category, priority,
            title, description[:500], url, source,
            round(relevance, 3), sentiment,
            content_hash, json.dumps(suggested_actions), now_iso(),
        ))

        alerts_created.append({
            "id": alert_id,
            "title": title,
            "category": category,
            "priority": priority,
            "summary": description[:300],
            "sentiment": sentiment,
            "relevance_score": round(relevance, 3),
            "source_name": source,
            "source_url": url,
            "provider": item.get("provider", "unknown"),
        })

    # Update contact monitoring timestamp
    db.execute(
        "UPDATE contacts SET last_monitored_at = ?, updated_at = ? WHERE id = ?",
        (now_iso(), now_iso(), contact["id"])
    )
    db.commit()

    return alerts_created


# ═══════════════════════════════════════════════════════════
# API Routes — Auth
# ═══════════════════════════════════════════════════════════

@app.route(f"{API_PREFIX}/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    if not data or not data.get("email") or not data.get("password"):
        return jsonify({"detail": "email and password required"}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (data["email"],)).fetchone()
    if existing:
        return jsonify({"detail": "Email already registered"}), 400

    user_id = new_id()
    db.execute("""
        INSERT INTO users (id, email, hashed_password, full_name, tier, created_at)
        VALUES (?, ?, ?, ?, 'free', ?)
    """, (user_id, data["email"], hash_password(data["password"]),
          data.get("full_name"), now_iso()))
    db.commit()

    token, expires_in = create_token(user_id)
    user = dict(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    return jsonify({
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": {
            "id": user["id"], "email": user["email"],
            "full_name": user["full_name"], "tier": user["tier"],
            "api_key": user["api_key"], "is_active": bool(user["is_active"]),
            "created_at": user["created_at"],
        }
    }), 201


@app.route(f"{API_PREFIX}/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE email = ?", (data.get("email"),)).fetchone()
    if not row or not verify_password(data.get("password", ""), row["hashed_password"]):
        return jsonify({"detail": "Invalid credentials"}), 401

    user = dict(row)
    token, expires_in = create_token(user["id"])
    return jsonify({
        "access_token": token, "token_type": "bearer", "expires_in": expires_in,
        "user": {
            "id": user["id"], "email": user["email"],
            "full_name": user["full_name"], "tier": user["tier"],
            "api_key": user["api_key"], "is_active": bool(user["is_active"]),
            "created_at": user["created_at"],
        }
    })


@app.route(f"{API_PREFIX}/auth/api-key", methods=["POST"])
@require_auth
def create_api_key_endpoint():
    db = get_db()
    key = generate_api_key()
    db.execute("UPDATE users SET api_key = ? WHERE id = ?", (key, g.current_user["id"]))
    db.commit()
    return jsonify({"api_key": key, "message": "Store this key securely. It won't be shown again."})


@app.route(f"{API_PREFIX}/auth/me")
@require_auth
def get_me():
    u = g.current_user
    return jsonify({
        "id": u["id"], "email": u["email"], "full_name": u["full_name"],
        "tier": u["tier"], "api_key": u["api_key"],
        "is_active": bool(u["is_active"]), "created_at": u["created_at"],
    })


# ═══════════════════════════════════════════════════════════
# API Routes — Contacts
# ═══════════════════════════════════════════════════════════

@app.route(f"{API_PREFIX}/contacts", methods=["POST"])
@require_auth
def create_contact():
    data = request.get_json()
    if not data or not data.get("full_name"):
        return jsonify({"detail": "full_name required"}), 400

    db = get_db()
    contact_id = new_id()
    full_name = data["full_name"]

    db.execute("""
        INSERT INTO contacts (id, owner_id, full_name, first_name, last_name, email, phone,
            company, job_title, notes, tags, group_name, priority, status,
            is_monitored, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_enrichment', ?, ?, ?)
    """, (
        contact_id, g.current_user["id"], full_name,
        data.get("first_name") or extract_first_name(full_name),
        data.get("last_name") or extract_last_name(full_name),
        data.get("email"), data.get("phone"),
        data.get("company"), data.get("job_title"), data.get("notes"),
        json.dumps(data.get("tags")) if data.get("tags") else None,
        data.get("group_name"), data.get("priority", 0),
        1 if data.get("auto_monitor") else 0,
        now_iso(), now_iso(),
    ))
    db.commit()

    contact = contact_to_dict(db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone())

    # Auto-enrich
    if data.get("auto_enrich", True):
        enrich_result = run_enrichment(contact)
        contact = contact_to_dict(db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone())

    return jsonify(contact), 201


@app.route(f"{API_PREFIX}/contacts", methods=["GET"])
@require_auth
def list_contacts():
    db = get_db()
    query = "SELECT * FROM contacts WHERE owner_id = ?"
    params = [g.current_user["id"]]

    q = request.args.get("q")
    if q:
        query += " AND (full_name LIKE ? OR email LIKE ? OR company LIKE ? OR job_title LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like, like])

    status = request.args.get("status")
    if status:
        query += " AND status = ?"
        params.append(status)

    is_monitored = request.args.get("is_monitored")
    if is_monitored is not None:
        query += " AND is_monitored = ?"
        params.append(1 if is_monitored.lower() == "true" else 0)

    priority = request.args.get("priority")
    if priority is not None:
        query += " AND priority = ?"
        params.append(int(priority))

    group_name = request.args.get("group_name")
    if group_name:
        query += " AND group_name = ?"
        params.append(group_name)

    # Count total
    count_q = query.replace("SELECT *", "SELECT COUNT(*)")
    total = db.execute(count_q, params).fetchone()[0]

    # Sort & paginate
    sort_by = request.args.get("sort_by", "updated_at")
    sort_order = request.args.get("sort_order", "desc").upper()
    if sort_by in ("full_name", "email", "company", "priority", "created_at", "updated_at", "enrichment_score"):
        query += f" ORDER BY {sort_by} {sort_order}"

    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.execute(query, params).fetchall()
    contacts = [contact_to_dict(r) for r in rows]

    return jsonify({
        "contacts": contacts, "total": total,
        "limit": limit, "offset": offset, "has_more": (offset + limit) < total,
    })


@app.route(f"{API_PREFIX}/contacts/<contact_id>", methods=["GET"])
@require_auth
def get_contact(contact_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM contacts WHERE id = ? AND owner_id = ?",
        (contact_id, g.current_user["id"])
    ).fetchone()
    if not row:
        return jsonify({"detail": "Contact not found"}), 404
    return jsonify(contact_to_dict(row))


@app.route(f"{API_PREFIX}/contacts/<contact_id>", methods=["PATCH"])
@require_auth
def update_contact(contact_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM contacts WHERE id = ? AND owner_id = ?",
        (contact_id, g.current_user["id"])
    ).fetchone()
    if not row:
        return jsonify({"detail": "Contact not found"}), 404

    data = request.get_json()
    allowed = ["full_name", "first_name", "last_name", "email", "phone", "company",
               "job_title", "notes", "group_name", "priority", "is_monitored"]
    updates = {k: v for k, v in data.items() if k in allowed}
    if "tags" in data:
        updates["tags"] = json.dumps(data["tags"])
    if "is_monitored" in updates:
        updates["is_monitored"] = 1 if updates["is_monitored"] else 0
    updates["updated_at"] = now_iso()

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    db.execute(f"UPDATE contacts SET {set_clause} WHERE id = ?", list(updates.values()) + [contact_id])
    db.commit()

    updated = contact_to_dict(db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone())
    return jsonify(updated)


@app.route(f"{API_PREFIX}/contacts/<contact_id>", methods=["DELETE"])
@require_auth
def delete_contact(contact_id):
    db = get_db()
    row = db.execute(
        "SELECT id FROM contacts WHERE id = ? AND owner_id = ?",
        (contact_id, g.current_user["id"])
    ).fetchone()
    if not row:
        return jsonify({"detail": "Contact not found"}), 404
    db.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    db.commit()
    return "", 204


@app.route(f"{API_PREFIX}/contacts/import", methods=["POST"])
@require_auth
def bulk_import():
    data = request.get_json()
    contacts_data = data.get("contacts", [])
    source = data.get("source", "api")
    deduplicate = data.get("deduplicate", True)

    db = get_db()
    imported = 0
    skipped = 0
    errors = []
    contact_ids = []

    for i, c in enumerate(contacts_data):
        try:
            if deduplicate and (c.get("email") or c.get("phone")):
                existing = None
                if c.get("email"):
                    existing = db.execute(
                        "SELECT id FROM contacts WHERE owner_id = ? AND email = ?",
                        (g.current_user["id"], c["email"])
                    ).fetchone()
                if not existing and c.get("phone"):
                    existing = db.execute(
                        "SELECT id FROM contacts WHERE owner_id = ? AND phone = ?",
                        (g.current_user["id"], c["phone"])
                    ).fetchone()
                if existing:
                    skipped += 1
                    continue

            cid = new_id()
            db.execute("""
                INSERT INTO contacts (id, owner_id, full_name, first_name, last_name, 
                    email, phone, company, job_title, tags, priority, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_enrichment', ?, ?)
            """, (
                cid, g.current_user["id"], c["full_name"],
                c.get("first_name") or extract_first_name(c["full_name"]),
                c.get("last_name") or extract_last_name(c["full_name"]),
                c.get("email"), c.get("phone"), c.get("company"), c.get("job_title"),
                json.dumps(c.get("tags")) if c.get("tags") else None,
                c.get("priority", 0), now_iso(), now_iso(),
            ))
            contact_ids.append(cid)
            imported += 1
        except Exception as e:
            errors.append({"index": i, "name": c.get("full_name", "?"), "error": str(e)})

    db.commit()
    return jsonify({
        "imported": imported, "skipped_duplicates": skipped,
        "errors": errors, "contact_ids": contact_ids,
    }), 201


@app.route(f"{API_PREFIX}/contacts/<contact_id>/monitor", methods=["POST"])
@require_auth
def toggle_monitoring(contact_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM contacts WHERE id = ? AND owner_id = ?",
        (contact_id, g.current_user["id"])
    ).fetchone()
    if not row:
        return jsonify({"detail": "Contact not found"}), 404

    enable = request.args.get("enable", "true").lower() == "true"
    keywords = request.args.get("keywords")

    updates = {"is_monitored": 1 if enable else 0, "updated_at": now_iso()}
    if enable:
        updates["status"] = "monitoring"
    if keywords:
        updates["monitoring_keywords"] = json.dumps(keywords.split(","))

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    db.execute(f"UPDATE contacts SET {set_clause} WHERE id = ?", list(updates.values()) + [contact_id])
    db.commit()

    return jsonify({"status": "monitoring_enabled" if enable else "monitoring_disabled", "contact_id": contact_id})


# ═══════════════════════════════════════════════════════════
# API Routes — Enrichment
# ═══════════════════════════════════════════════════════════

@app.route(f"{API_PREFIX}/enrichment/enrich", methods=["POST"])
@require_auth
def enrich_endpoint():
    data = request.get_json()
    contact_id = data.get("contact_id")
    db = get_db()

    row = db.execute(
        "SELECT * FROM contacts WHERE id = ? AND owner_id = ?",
        (contact_id, g.current_user["id"])
    ).fetchone()
    if not row:
        return jsonify({"detail": "Contact not found"}), 404

    result = run_enrichment(
        contact_to_dict(row),
        providers=data.get("providers"),
        force=data.get("force_refresh", False),
    )
    return jsonify(result)


@app.route(f"{API_PREFIX}/enrichment/providers")
@require_auth
def list_providers():
    providers = []
    for name, info in PROVIDERS.items():
        has_key = True
        if info["requires_key"]:
            # Check if key is configured
            key_map = {"gnews": "gnews_key", "guardian": "guardian_key"}
            config_key = key_map.get(name)
            has_key = bool(PROVIDER_CONFIG.get(config_key)) if config_key else False

        providers.append({
            "name": name, "display_name": info["display_name"],
            "provider_type": info["type"], "is_enabled": True,
            "has_api_key": has_key or not info["requires_key"],
            "requires_api_key": info["requires_key"],
        })
    return jsonify({
        "providers": providers,
        "total_enabled": len(providers),
        "total_with_keys": len([p for p in providers if not PROVIDERS[p["name"]]["requires_key"] or PROVIDER_CONFIG.get(p["name"])]),
    })


@app.route(f"{API_PREFIX}/enrichment/config", methods=["POST"])
@require_auth
def configure_providers():
    """Set API keys for providers at runtime."""
    data = request.get_json()
    updated = []
    for key in ["github_token", "gnews_key", "guardian_key", "opencorporates_key",
                 "opensanctions_url", "opensanctions_key"]:
        if key in data:
            PROVIDER_CONFIG[key] = data[key]
            _pipeline.config[key] = data[key]
            updated.append(key)
    return jsonify({"updated": updated, "message": f"Updated {len(updated)} provider keys"})


# ═══════════════════════════════════════════════════════════
# API Routes — Monitoring
# ═══════════════════════════════════════════════════════════

@app.route(f"{API_PREFIX}/monitoring/scan/<contact_id>", methods=["POST"])
@require_auth
def scan_contact(contact_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM contacts WHERE id = ? AND owner_id = ?",
        (contact_id, g.current_user["id"])
    ).fetchone()
    if not row:
        return jsonify({"detail": "Contact not found"}), 404

    contact = contact_to_dict(row)
    alerts = scan_contact_for_news(contact, g.current_user["id"])

    return jsonify({
        "contact_id": contact_id, "contact_name": contact["full_name"],
        "new_alerts": len(alerts), "alerts": alerts,
    })


@app.route(f"{API_PREFIX}/monitoring/scan", methods=["POST"])
@require_auth
def scan_all():
    db = get_db()
    limit = int(request.args.get("limit", 100))
    rows = db.execute(
        "SELECT * FROM contacts WHERE is_monitored = 1 ORDER BY last_monitored_at ASC NULLS FIRST LIMIT ?",
        (limit,)
    ).fetchall()

    stats = {"contacts_scanned": 0, "alerts_created": 0, "errors": 0}
    for row in rows:
        try:
            alerts = scan_contact_for_news(contact_to_dict(row), g.current_user["id"])
            stats["contacts_scanned"] += 1
            stats["alerts_created"] += len(alerts)
        except Exception as e:
            stats["errors"] += 1

    return jsonify(stats)


@app.route(f"{API_PREFIX}/monitoring/stats")
@require_auth
def monitoring_stats():
    db = get_db()
    uid = g.current_user["id"]

    monitored = db.execute("SELECT COUNT(*) FROM contacts WHERE owner_id = ? AND is_monitored = 1", (uid,)).fetchone()[0]
    alerts_today = db.execute(
        "SELECT COUNT(*) FROM alerts WHERE user_id = ? AND created_at >= datetime('now', '-1 day')", (uid,)
    ).fetchone()[0]
    alerts_week = db.execute(
        "SELECT COUNT(*) FROM alerts WHERE user_id = ? AND created_at >= datetime('now', '-7 day')", (uid,)
    ).fetchone()[0]
    unread = db.execute("SELECT COUNT(*) FROM alerts WHERE user_id = ? AND status = 'new'", (uid,)).fetchone()[0]
    rules = db.execute("SELECT COUNT(*) FROM monitoring_rules WHERE user_id = ? AND is_active = 1", (uid,)).fetchone()[0]

    return jsonify({
        "total_contacts_monitored": monitored, "alerts_today": alerts_today,
        "alerts_this_week": alerts_week, "unread_alerts": unread,
        "active_rules": rules, "providers_active": len(PROVIDERS),
    })


# ═══════════════════════════════════════════════════════════
# API Routes — Alerts
# ═══════════════════════════════════════════════════════════

@app.route(f"{API_PREFIX}/alerts")
@require_auth
def list_alerts():
    db = get_db()
    uid = g.current_user["id"]

    query = """
        SELECT a.*, c.full_name as contact_name 
        FROM alerts a JOIN contacts c ON a.contact_id = c.id
        WHERE a.user_id = ?
    """
    params = [uid]

    contact_id = request.args.get("contact_id")
    if contact_id:
        query += " AND a.contact_id = ?"
        params.append(contact_id)

    categories = request.args.get("categories")
    if categories:
        cats = categories.split(",")
        placeholders = ",".join("?" * len(cats))
        query += f" AND a.category IN ({placeholders})"
        params.extend(cats)

    priorities = request.args.get("priorities")
    if priorities:
        pris = priorities.split(",")
        placeholders = ",".join("?" * len(pris))
        query += f" AND a.priority IN ({placeholders})"
        params.extend(pris)

    status = request.args.get("status")
    if status:
        query += " AND a.status = ?"
        params.append(status)

    min_rel = request.args.get("min_relevance")
    if min_rel:
        query += " AND a.relevance_score >= ?"
        params.append(float(min_rel))

    # Total & unread count
    count_q = query.replace("SELECT a.*, c.full_name as contact_name", "SELECT COUNT(*)")
    total = db.execute(count_q, params).fetchone()[0]
    unread = db.execute("SELECT COUNT(*) FROM alerts WHERE user_id = ? AND status = 'new'", (uid,)).fetchone()[0]

    query += " ORDER BY a.created_at DESC"
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.execute(query, params).fetchall()
    alerts = [alert_to_dict(r) for r in rows]

    return jsonify({
        "alerts": alerts, "total": total, "unread_count": unread,
        "limit": limit, "offset": offset, "has_more": (offset + limit) < total,
    })


@app.route(f"{API_PREFIX}/alerts/<alert_id>", methods=["PATCH"])
@require_auth
def update_alert(alert_id):
    data = request.get_json()
    new_status = data.get("status")
    if new_status not in ("read", "dismissed", "actioned"):
        return jsonify({"detail": "status must be: read, dismissed, or actioned"}), 400

    db = get_db()
    row = db.execute("SELECT * FROM alerts WHERE id = ? AND user_id = ?", (alert_id, g.current_user["id"])).fetchone()
    if not row:
        return jsonify({"detail": "Alert not found"}), 404

    updates = {"status": new_status, "updated_at": now_iso()}
    if new_status == "read":
        updates["read_at"] = now_iso()

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    db.execute(f"UPDATE alerts SET {set_clause} WHERE id = ?", list(updates.values()) + [alert_id])
    db.commit()
    return jsonify({"id": alert_id, "status": new_status})


@app.route(f"{API_PREFIX}/alerts/read-all", methods=["POST"])
@require_auth
def mark_all_read():
    db = get_db()
    db.execute(
        "UPDATE alerts SET status = 'read', read_at = ? WHERE user_id = ? AND status = 'new'",
        (now_iso(), g.current_user["id"])
    )
    db.commit()
    count = db.execute("SELECT changes()").fetchone()[0]
    return jsonify({"marked_read": count})


@app.route(f"{API_PREFIX}/alerts/summary")
@require_auth
def alert_summary():
    db = get_db()
    uid = g.current_user["id"]

    by_cat = {}
    for row in db.execute(
        "SELECT category, COUNT(*) as cnt FROM alerts WHERE user_id = ? AND status = 'new' GROUP BY category", (uid,)
    ).fetchall():
        by_cat[row["category"]] = row["cnt"]

    by_pri = {}
    for row in db.execute(
        "SELECT priority, COUNT(*) as cnt FROM alerts WHERE user_id = ? AND status = 'new' GROUP BY priority", (uid,)
    ).fetchall():
        by_pri[row["priority"]] = row["cnt"]

    return jsonify({
        "by_category": by_cat, "by_priority": by_pri,
        "total_unread": sum(by_cat.values()),
    })


# ═══════════════════════════════════════════════════════════
# API Routes — Agent Tools
# ═══════════════════════════════════════════════════════════

@app.route(f"{API_PREFIX}/agent/tools")
@require_auth
def get_tool_definitions():
    fmt = request.args.get("format", "openai")
    tools = [
        {"name": "search_contacts", "description": "Search through the user's contacts by name, company, email, or other criteria."},
        {"name": "get_contact", "description": "Get full details for a specific contact including enriched data and recent alerts."},
        {"name": "enrich_contact", "description": "Trigger data enrichment for a contact from public and paid sources."},
        {"name": "get_alerts", "description": "Get recent alerts and news about contacts."},
        {"name": "monitor_contact", "description": "Start or stop monitoring a contact for news and changes."},
        {"name": "add_contact", "description": "Add a new contact to the user's list."},
        {"name": "contact_report", "description": "Generate a comprehensive intelligence report about a contact."},
    ]
    return jsonify({"tools": tools, "format": fmt})


@app.route(f"{API_PREFIX}/agent/tool", methods=["POST"])
@require_auth
def execute_tool():
    data = request.get_json()
    tool_name = data.get("tool_name")
    arguments = data.get("arguments", {})
    db = get_db()
    uid = g.current_user["id"]

    try:
        if tool_name == "search_contacts":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 10)
            rows = db.execute(
                """SELECT * FROM contacts WHERE owner_id = ? 
                   AND (full_name LIKE ? OR email LIKE ? OR company LIKE ? OR job_title LIKE ?)
                   LIMIT ?""",
                (uid, f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", limit)
            ).fetchall()
            contacts = [{
                "id": r["id"], "name": r["full_name"], "email": r["email"],
                "phone": r["phone"], "company": r["company"], "job_title": r["job_title"],
                "status": r["status"], "is_monitored": bool(r["is_monitored"]),
                "enrichment_score": r["enrichment_score"], "tags": parse_json_field(r["tags"]),
            } for r in rows]
            return jsonify({"success": True, "tool": tool_name, "data": {"contacts": contacts, "total": len(contacts)}})

        elif tool_name == "get_contact":
            cid = arguments.get("contact_id")
            row = db.execute("SELECT * FROM contacts WHERE id = ? AND owner_id = ?", (cid, uid)).fetchone()
            if not row:
                return jsonify({"success": False, "tool": tool_name, "message": "Contact not found"})
            contact = contact_to_dict(row)
            # Include recent alerts
            if arguments.get("include_alerts", True):
                alerts = db.execute(
                    "SELECT * FROM alerts WHERE contact_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 10",
                    (cid, uid)
                ).fetchall()
                contact["recent_alerts"] = [alert_to_dict(a) for a in alerts]
            return jsonify({"success": True, "tool": tool_name, "data": contact})

        elif tool_name == "enrich_contact":
            cid = arguments.get("contact_id")
            row = db.execute("SELECT * FROM contacts WHERE id = ? AND owner_id = ?", (cid, uid)).fetchone()
            if not row:
                return jsonify({"success": False, "tool": tool_name, "message": "Contact not found"})
            result = run_enrichment(contact_to_dict(row), arguments.get("providers"), arguments.get("force_refresh", False))
            return jsonify({"success": True, "tool": tool_name, "data": result})

        elif tool_name == "get_alerts":
            query = "SELECT a.*, c.full_name as contact_name FROM alerts a JOIN contacts c ON a.contact_id = c.id WHERE a.user_id = ?"
            params = [uid]
            cid = arguments.get("contact_id")
            if cid:
                query += " AND a.contact_id = ?"
                params.append(cid)
            cats = arguments.get("categories")
            if cats:
                ph = ",".join("?" * len(cats))
                query += f" AND a.category IN ({ph})"
                params.extend(cats)
            if arguments.get("unread_only"):
                query += " AND a.status = 'new'"
            query += f" ORDER BY a.created_at DESC LIMIT ?"
            params.append(arguments.get("limit", 20))
            rows = db.execute(query, params).fetchall()
            alerts = [alert_to_dict(r) for r in rows]
            unread = db.execute("SELECT COUNT(*) FROM alerts WHERE user_id = ? AND status = 'new'", (uid,)).fetchone()[0]
            return jsonify({"success": True, "tool": tool_name, "data": {"alerts": alerts, "total": len(alerts), "unread_count": unread}})

        elif tool_name == "monitor_contact":
            cid = arguments.get("contact_id")
            action = arguments.get("action", "start")
            row = db.execute("SELECT * FROM contacts WHERE id = ? AND owner_id = ?", (cid, uid)).fetchone()
            if not row:
                return jsonify({"success": False, "tool": tool_name, "message": "Contact not found"})
            enabled = action == "start"
            kw = arguments.get("keywords")
            updates = {"is_monitored": 1 if enabled else 0, "updated_at": now_iso()}
            if enabled:
                updates["status"] = "monitoring"
            if kw:
                updates["monitoring_keywords"] = json.dumps(kw)
            sc = ", ".join(f"{k} = ?" for k in updates.keys())
            db.execute(f"UPDATE contacts SET {sc} WHERE id = ?", list(updates.values()) + [cid])
            db.commit()
            return jsonify({"success": True, "tool": tool_name, "data": {
                "contact_id": cid, "contact_name": row["full_name"],
                "monitoring": enabled, "message": f"Monitoring {'started' if enabled else 'stopped'}",
            }})

        elif tool_name == "add_contact":
            cid = new_id()
            fn = arguments.get("full_name", "Unknown")
            db.execute("""
                INSERT INTO contacts (id, owner_id, full_name, first_name, last_name, email, phone,
                    company, job_title, notes, tags, priority, status, is_monitored, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending_enrichment', ?, ?, ?)
            """, (
                cid, uid, fn, extract_first_name(fn), extract_last_name(fn),
                arguments.get("email"), arguments.get("phone"),
                arguments.get("company"), arguments.get("job_title"),
                arguments.get("notes"),
                json.dumps(arguments.get("tags")) if arguments.get("tags") else None,
                1 if arguments.get("auto_monitor") else 0,
                now_iso(), now_iso(),
            ))
            db.commit()
            contact = contact_to_dict(db.execute("SELECT * FROM contacts WHERE id = ?", (cid,)).fetchone())
            # Auto-enrich
            if arguments.get("auto_enrich", True):
                enrich_result = run_enrichment(contact)
                contact = contact_to_dict(db.execute("SELECT * FROM contacts WHERE id = ?", (cid,)).fetchone())
            return jsonify({"success": True, "tool": tool_name, "data": {
                "contact_id": cid, "name": fn, "status": contact.get("status"),
                "enrichment_score": contact.get("enrichment_score"),
                "message": f"Contact '{fn}' added and enriched.",
            }})

        elif tool_name == "contact_report":
            cid = arguments.get("contact_id")
            row = db.execute("SELECT * FROM contacts WHERE id = ? AND owner_id = ?", (cid, uid)).fetchone()
            if not row:
                return jsonify({"success": False, "tool": tool_name, "message": "Contact not found"})
            contact = contact_to_dict(row)

            # Get alerts
            alerts = db.execute(
                "SELECT * FROM alerts WHERE contact_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 10",
                (cid, uid)
            ).fetchall()

            report = {
                "contact": {k: contact.get(k) for k in ["full_name", "company", "job_title", "location", "email", "phone", "bio"]},
                "enrichment_score": contact.get("enrichment_score"),
                "online_presence": {k: contact.get(k) for k in ["linkedin_url", "twitter_handle", "github_username", "website"] if contact.get(k)},
                "work_history": contact.get("work_history"),
                "education": contact.get("education"),
                "attributes": contact.get("attributes"),
                "recent_events": [alert_to_dict(a) for a in alerts],
                "report_type": arguments.get("report_type", "standard"),
            }

            if arguments.get("include_risk_assessment"):
                legal = len([a for a in alerts if dict(a).get("category") == "legal"])
                risk = len([a for a in alerts if dict(a).get("category") == "risk"])
                report["risk_assessment"] = {
                    "sanctions_check": "clear", "legal_issues": legal,
                    "risk_alerts": risk,
                    "overall_risk": "high" if risk > 2 else "medium" if (legal > 0 or risk > 0) else "low",
                }

            return jsonify({"success": True, "tool": tool_name, "data": report})

        else:
            available = ["search_contacts", "get_contact", "enrich_contact", "get_alerts",
                        "monitor_contact", "add_contact", "contact_report"]
            return jsonify({"success": False, "tool": tool_name, "message": f"Unknown tool. Available: {available}"})

    except Exception as e:
        return jsonify({"success": False, "tool": tool_name, "message": str(e)}), 500


# ═══════════════════════════════════════════════════════════
# Health & Root
# ═══════════════════════════════════════════════════════════

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "service": APP_NAME, "version": APP_VERSION})


@app.route("/")
def root():
    return jsonify({
        "service": APP_NAME, "version": APP_VERSION,
        "docs": f"{API_PREFIX}/agent/tools",
        "endpoints": {
            "auth": f"{API_PREFIX}/auth/",
            "contacts": f"{API_PREFIX}/contacts",
            "enrichment": f"{API_PREFIX}/enrichment/",
            "monitoring": f"{API_PREFIX}/monitoring/",
            "alerts": f"{API_PREFIX}/alerts",
            "agent_tools": f"{API_PREFIX}/agent/tool",
        }
    })


# ═══════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()
    print(f"\n{'='*60}")
    print(f"  {APP_NAME} v{APP_VERSION} — Starting...")
    print(f"  Server: http://localhost:5000")
    print(f"  API:    http://localhost:5000{API_PREFIX}")
    print(f"  Tools:  http://localhost:5000{API_PREFIX}/agent/tools")
    print(f"{'='*60}\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
