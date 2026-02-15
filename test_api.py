"""
ContactIQ — Full API Test Suite
Tests all modules: Auth, Contacts, Enrichment, Monitoring, Alerts, Agent Tools.
"""
import json
import sys
import os
import time
import threading
import requests
from datetime import datetime

BASE = "http://127.0.0.1:5000/api/v1"
PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
WARN = "\033[93m⚠ WARN\033[0m"
HEADER = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

results = {"passed": 0, "failed": 0, "total": 0}
TOKEN = None
API_KEY = None
USER_ID = None
CONTACT_IDS = []
ALERT_IDS = []


def test(name, response, expected_status=200, check_fn=None):
    """Run a single test assertion."""
    results["total"] += 1
    status_ok = response.status_code == expected_status

    try:
        body = response.json()
    except Exception:
        body = {}

    check_ok = True
    check_msg = ""
    if check_fn:
        try:
            check_ok = check_fn(body)
            if not check_ok:
                check_msg = f" | check failed on: {json.dumps(body)[:200]}"
        except Exception as e:
            check_ok = False
            check_msg = f" | check error: {e}"

    if status_ok and check_ok:
        results["passed"] += 1
        print(f"  {PASS} {name} [{response.status_code}]")
    else:
        results["failed"] += 1
        detail = body.get("detail", body.get("message", ""))
        print(f"  {FAIL} {name} [expected {expected_status}, got {response.status_code}] {detail}{check_msg}")
        if not status_ok:
            try:
                print(f"       Response: {json.dumps(body, indent=2)[:300]}")
            except:
                pass

    return body


def section(title):
    print(f"\n{HEADER}{'─'*60}")
    print(f"  {BOLD}{title}")
    print(f"{'─'*60}{RESET}")


def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def api_key_headers():
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}


# ═══════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════

def test_health():
    section("HEALTH CHECK")
    r = requests.get("http://127.0.0.1:5000/health")
    test("Health endpoint", r, 200, lambda b: b.get("status") == "healthy")

    r = requests.get("http://127.0.0.1:5000/")
    test("Root endpoint", r, 200, lambda b: "ContactIQ" in b.get("service", ""))


def test_auth():
    global TOKEN, API_KEY, USER_ID
    section("AUTHENTICATION")

    # Register
    r = requests.post(f"{BASE}/auth/register", json={
        "email": "test@contactiq.dev",
        "password": "testpass123",
        "full_name": "Test User",
    })
    body = test("Register new user", r, 201, lambda b: "access_token" in b)
    TOKEN = body.get("access_token")
    USER_ID = body.get("user", {}).get("id")

    # Duplicate registration
    r = requests.post(f"{BASE}/auth/register", json={
        "email": "test@contactiq.dev", "password": "another",
    })
    test("Reject duplicate email", r, 400)

    # Login
    r = requests.post(f"{BASE}/auth/login", json={
        "email": "test@contactiq.dev", "password": "testpass123",
    })
    body = test("Login", r, 200, lambda b: "access_token" in b)
    TOKEN = body.get("access_token")

    # Wrong password
    r = requests.post(f"{BASE}/auth/login", json={
        "email": "test@contactiq.dev", "password": "wrong",
    })
    test("Reject wrong password", r, 401)

    # Get me
    r = requests.get(f"{BASE}/auth/me", headers=auth_headers())
    test("Get current user", r, 200, lambda b: b.get("email") == "test@contactiq.dev")

    # Generate API key
    r = requests.post(f"{BASE}/auth/api-key", headers=auth_headers())
    body = test("Generate API key", r, 200, lambda b: b.get("api_key", "").startswith("ciq_"))
    API_KEY = body.get("api_key")

    # Auth with API key
    r = requests.get(f"{BASE}/auth/me", headers=api_key_headers())
    test("Auth with API key", r, 200, lambda b: b.get("email") == "test@contactiq.dev")

    # Reject no auth
    r = requests.get(f"{BASE}/auth/me")
    test("Reject no auth", r, 401)


def test_contacts():
    global CONTACT_IDS
    section("CONTACTS CRUD")

    # Create contacts
    contacts = [
        {"full_name": "Elon Musk", "email": "elon@tesla.com", "company": "Tesla", "job_title": "CEO", "priority": 2, "tags": ["vip", "tech"]},
        {"full_name": "Satya Nadella", "email": "satya@microsoft.com", "company": "Microsoft", "job_title": "CEO", "priority": 2, "tags": ["vip", "tech"]},
        {"full_name": "Jensen Huang", "email": "jensen@nvidia.com", "company": "NVIDIA", "job_title": "CEO", "priority": 1, "tags": ["tech", "ai"]},
        {"full_name": "Sam Altman", "email": "sam@openai.com", "company": "OpenAI", "job_title": "CEO", "priority": 2, "tags": ["ai", "vip"]},
        {"full_name": "Dario Amodei", "email": "dario@anthropic.com", "company": "Anthropic", "job_title": "CEO", "priority": 1, "tags": ["ai"]},
    ]

    for c in contacts:
        r = requests.post(f"{BASE}/contacts", json=c, headers=auth_headers())
        body = test(f"Create contact: {c['full_name']}", r, 201,
                    lambda b: b.get("full_name") == c["full_name"] and b.get("status") in ("enriched", "pending_enrichment"))
        CONTACT_IDS.append(body.get("id"))

    # List all
    r = requests.get(f"{BASE}/contacts", headers=auth_headers())
    body = test("List all contacts", r, 200, lambda b: b.get("total") == 5)

    # Search
    r = requests.get(f"{BASE}/contacts?q=Tesla", headers=auth_headers())
    body = test("Search contacts (Tesla)", r, 200,
                lambda b: b.get("total") >= 1 and any("Elon" in c.get("full_name", "") for c in b.get("contacts", [])))

    # Search by tag (not directly supported via query param but test generic search)
    r = requests.get(f"{BASE}/contacts?q=CEO", headers=auth_headers())
    test("Search contacts (CEO)", r, 200, lambda b: b.get("total") >= 1)

    # Get single contact
    r = requests.get(f"{BASE}/contacts/{CONTACT_IDS[0]}", headers=auth_headers())
    body = test("Get single contact", r, 200, lambda b: b.get("full_name") == "Elon Musk")

    # Check enrichment was applied
    test("Contact was enriched", r, 200,
         lambda b: b.get("enrichment_score") is not None and b.get("enrichment_score") > 0)

    # Update contact
    r = requests.patch(f"{BASE}/contacts/{CONTACT_IDS[0]}",
                       json={"job_title": "Technoking", "notes": "Updated via test"},
                       headers=auth_headers())
    test("Update contact", r, 200,
         lambda b: b.get("job_title") == "Technoking" and b.get("notes") == "Updated via test")

    # 404
    r = requests.get(f"{BASE}/contacts/nonexistent-id", headers=auth_headers())
    test("Get nonexistent contact → 404", r, 404)


def test_bulk_import():
    section("BULK IMPORT")

    r = requests.post(f"{BASE}/contacts/import", json={
        "contacts": [
            {"full_name": "Bill Gates", "email": "bill@gates.com", "company": "Gates Foundation"},
            {"full_name": "Tim Cook", "email": "tim@apple.com", "company": "Apple", "job_title": "CEO"},
            {"full_name": "Sundar Pichai", "email": "sundar@google.com", "company": "Google"},
            # Duplicate email test
            {"full_name": "Elon Duplicate", "email": "elon@tesla.com", "company": "Tesla"},
        ],
        "source": "csv",
        "deduplicate": True,
    }, headers=auth_headers())

    body = test("Bulk import 4 contacts (1 duplicate)", r, 201,
                lambda b: b.get("imported") == 3 and b.get("skipped_duplicates") == 1)

    CONTACT_IDS.extend(body.get("contact_ids", []))

    # Verify total
    r = requests.get(f"{BASE}/contacts", headers=auth_headers())
    test("Total contacts after import", r, 200, lambda b: b.get("total") == 8)


def test_enrichment():
    section("ENRICHMENT")

    # Enrich a specific contact
    r = requests.post(f"{BASE}/enrichment/enrich", json={
        "contact_id": CONTACT_IDS[0],
        "force_refresh": True,
    }, headers=auth_headers())
    body = test("Enrich contact (force refresh)", r, 200,
                lambda b: b.get("status") == "completed" and len(b.get("providers_used", [])) > 0)

    print(f"       Enrichment score: {body.get('enrichment_score', 0)}%")
    print(f"       Providers used: {body.get('providers_used', [])}")
    print(f"       Total cost: ${body.get('total_cost_usd', 0):.4f}")

    # Enrich with specific providers
    r = requests.post(f"{BASE}/enrichment/enrich", json={
        "contact_id": CONTACT_IDS[1],
        "providers": ["github", "opensanctions"],
    }, headers=auth_headers())
    test("Enrich with specific providers", r, 200,
         lambda b: b.get("status") == "completed")

    # List providers
    r = requests.get(f"{BASE}/enrichment/providers", headers=auth_headers())
    test("List enrichment providers", r, 200,
         lambda b: len(b.get("providers", [])) >= 8)


def test_monitoring():
    section("MONITORING")

    # Enable monitoring for contacts
    for i, cid in enumerate(CONTACT_IDS[:3]):
        r = requests.post(f"{BASE}/contacts/{cid}/monitor?enable=true&keywords=AI,funding",
                         headers=auth_headers())
        test(f"Enable monitoring for contact #{i+1}", r, 200,
             lambda b: "enabled" in b.get("status", ""))

    # Scan a single contact
    r = requests.post(f"{BASE}/monitoring/scan/{CONTACT_IDS[0]}", headers=auth_headers())
    body = test("Scan single contact for news", r, 200,
                lambda b: "new_alerts" in b)
    alerts_count = body.get("new_alerts", 0)
    print(f"       New alerts generated: {alerts_count}")
    if body.get("alerts"):
        for a in body["alerts"][:3]:
            print(f"       → [{a.get('category')}] {a.get('title', '')[:60]}")

    # Scan all monitored contacts
    r = requests.post(f"{BASE}/monitoring/scan", headers=auth_headers())
    body = test("Scan all monitored contacts", r, 200,
                lambda b: "contacts_scanned" in b)
    print(f"       Contacts scanned: {body.get('contacts_scanned', 0)}")
    print(f"       Alerts created: {body.get('alerts_created', 0)}")

    # Monitoring stats
    r = requests.get(f"{BASE}/monitoring/stats", headers=auth_headers())
    body = test("Get monitoring stats", r, 200,
                lambda b: b.get("total_contacts_monitored", 0) >= 3)
    print(f"       Monitored: {body.get('total_contacts_monitored', 0)}")
    print(f"       Unread alerts: {body.get('unread_alerts', 0)}")

    # Disable monitoring
    r = requests.post(f"{BASE}/contacts/{CONTACT_IDS[2]}/monitor?enable=false",
                     headers=auth_headers())
    test("Disable monitoring", r, 200, lambda b: "disabled" in b.get("status", ""))


def test_alerts():
    global ALERT_IDS
    section("ALERTS")

    # List all alerts
    r = requests.get(f"{BASE}/alerts", headers=auth_headers())
    body = test("List all alerts", r, 200, lambda b: b.get("total", 0) > 0)
    print(f"       Total alerts: {body.get('total', 0)}")
    print(f"       Unread: {body.get('unread_count', 0)}")

    if body.get("alerts"):
        ALERT_IDS = [a["id"] for a in body["alerts"]]

    # Filter by category
    r = requests.get(f"{BASE}/alerts?categories=career", headers=auth_headers())
    body = test("Filter alerts by career category", r, 200)
    career_count = body.get("total", 0)
    print(f"       Career alerts: {career_count}")

    # Filter by priority
    r = requests.get(f"{BASE}/alerts?priorities=critical,high", headers=auth_headers())
    test("Filter alerts by priority (critical+high)", r, 200)

    # Filter by contact
    if CONTACT_IDS:
        r = requests.get(f"{BASE}/alerts?contact_id={CONTACT_IDS[0]}", headers=auth_headers())
        test("Filter alerts by contact", r, 200)

    # Alert summary
    r = requests.get(f"{BASE}/alerts/summary", headers=auth_headers())
    body = test("Alert summary by category/priority", r, 200,
                lambda b: "by_category" in b and "by_priority" in b)
    print(f"       By category: {body.get('by_category', {})}")
    print(f"       By priority: {body.get('by_priority', {})}")

    # Mark alert as read
    if ALERT_IDS:
        r = requests.patch(f"{BASE}/alerts/{ALERT_IDS[0]}",
                          json={"status": "read"}, headers=auth_headers())
        test("Mark alert as read", r, 200, lambda b: b.get("status") == "read")

    # Mark all read
    r = requests.post(f"{BASE}/alerts/read-all", headers=auth_headers())
    test("Mark all alerts as read", r, 200, lambda b: b.get("marked_read", -1) >= 0)


def test_agent_tools():
    section("AGENT TOOLS (AI Integration)")

    # Get tool definitions
    r = requests.get(f"{BASE}/agent/tools", headers=api_key_headers())
    body = test("Get tool definitions (OpenAI format)", r, 200,
                lambda b: len(b.get("tools", [])) >= 7)
    print(f"       Available tools: {[t['name'] for t in body.get('tools', [])]}")

    # Tool: search_contacts
    r = requests.post(f"{BASE}/agent/tool", json={
        "tool_name": "search_contacts",
        "arguments": {"query": "CEO", "limit": 5}
    }, headers=api_key_headers())
    body = test("Agent tool: search_contacts", r, 200,
                lambda b: b.get("success") and len(b.get("data", {}).get("contacts", [])) > 0)
    found = body.get("data", {}).get("contacts", [])
    print(f"       Found {len(found)} contacts matching 'CEO'")

    # Tool: get_contact
    if CONTACT_IDS:
        r = requests.post(f"{BASE}/agent/tool", json={
            "tool_name": "get_contact",
            "arguments": {"contact_id": CONTACT_IDS[0], "include_alerts": True}
        }, headers=api_key_headers())
        body = test("Agent tool: get_contact", r, 200,
                    lambda b: b.get("success") and b.get("data", {}).get("full_name"))
        contact = body.get("data", {})
        print(f"       Contact: {contact.get('full_name')} @ {contact.get('company')}")
        print(f"       Enrichment: {contact.get('enrichment_score')}%")
        print(f"       Alerts: {len(contact.get('recent_alerts', []))}")

    # Tool: add_contact
    r = requests.post(f"{BASE}/agent/tool", json={
        "tool_name": "add_contact",
        "arguments": {
            "full_name": "Agent Added Contact",
            "email": "agent@test.com",
            "company": "Agent Corp",
            "job_title": "AI Engineer",
            "tags": ["agent-added"],
            "auto_enrich": True,
        }
    }, headers=api_key_headers())
    body = test("Agent tool: add_contact (with auto-enrich)", r, 200,
                lambda b: b.get("success") and b.get("data", {}).get("contact_id"))
    agent_contact_id = body.get("data", {}).get("contact_id")
    print(f"       Created: {body.get('data', {}).get('name')}")
    print(f"       Enrichment: {body.get('data', {}).get('enrichment_score')}%")

    # Tool: enrich_contact
    if agent_contact_id:
        r = requests.post(f"{BASE}/agent/tool", json={
            "tool_name": "enrich_contact",
            "arguments": {"contact_id": agent_contact_id, "force_refresh": True}
        }, headers=api_key_headers())
        body = test("Agent tool: enrich_contact", r, 200,
                    lambda b: b.get("success") and b.get("data", {}).get("status") == "completed")

    # Tool: monitor_contact
    if CONTACT_IDS:
        r = requests.post(f"{BASE}/agent/tool", json={
            "tool_name": "monitor_contact",
            "arguments": {
                "contact_id": CONTACT_IDS[3],
                "action": "start",
                "keywords": ["GPT", "AGI", "fundraising"],
            }
        }, headers=api_key_headers())
        body = test("Agent tool: monitor_contact (start)", r, 200,
                    lambda b: b.get("success") and b.get("data", {}).get("monitoring") == True)

    # Tool: get_alerts
    r = requests.post(f"{BASE}/agent/tool", json={
        "tool_name": "get_alerts",
        "arguments": {"limit": 10, "unread_only": False}
    }, headers=api_key_headers())
    body = test("Agent tool: get_alerts", r, 200,
                lambda b: b.get("success") and "alerts" in b.get("data", {}))
    print(f"       Total alerts: {body.get('data', {}).get('total', 0)}")

    # Tool: contact_report
    if CONTACT_IDS:
        r = requests.post(f"{BASE}/agent/tool", json={
            "tool_name": "contact_report",
            "arguments": {
                "contact_id": CONTACT_IDS[0],
                "report_type": "deep",
                "include_risk_assessment": True,
            }
        }, headers=api_key_headers())
        body = test("Agent tool: contact_report (deep + risk)", r, 200,
                    lambda b: b.get("success") and "risk_assessment" in b.get("data", {}))
        report = body.get("data", {})
        print(f"       Report for: {report.get('contact', {}).get('full_name')}")
        print(f"       Risk level: {report.get('risk_assessment', {}).get('overall_risk')}")
        print(f"       Online: {list(report.get('online_presence', {}).keys())}")

    # Tool: unknown tool
    r = requests.post(f"{BASE}/agent/tool", json={
        "tool_name": "nonexistent_tool",
        "arguments": {}
    }, headers=api_key_headers())
    test("Agent tool: unknown tool → graceful error", r, 200,
         lambda b: b.get("success") == False and "Unknown" in b.get("message", ""))


def test_pagination_and_sorting():
    section("PAGINATION & SORTING")

    # Paginated list
    r = requests.get(f"{BASE}/contacts?limit=3&offset=0&sort_by=full_name&sort_order=asc",
                    headers=auth_headers())
    body = test("Paginated contacts (page 1, limit=3)", r, 200,
                lambda b: len(b.get("contacts", [])) <= 3 and b.get("has_more") == True)

    # Page 2
    r = requests.get(f"{BASE}/contacts?limit=3&offset=3&sort_by=full_name&sort_order=asc",
                    headers=auth_headers())
    test("Paginated contacts (page 2)", r, 200)

    # Sort by enrichment score
    r = requests.get(f"{BASE}/contacts?sort_by=enrichment_score&sort_order=desc&limit=5",
                    headers=auth_headers())
    test("Sort by enrichment score (desc)", r, 200)


def test_delete_contact():
    section("DELETE")

    if len(CONTACT_IDS) > 5:
        cid = CONTACT_IDS[-1]
        r = requests.delete(f"{BASE}/contacts/{cid}", headers=auth_headers())
        test("Delete contact", r, 204)

        r = requests.get(f"{BASE}/contacts/{cid}", headers=auth_headers())
        test("Verify deleted contact → 404", r, 404)


def test_edge_cases():
    section("EDGE CASES")

    # Empty search
    r = requests.get(f"{BASE}/contacts?q=zzzznonexistent", headers=auth_headers())
    test("Search with no results", r, 200, lambda b: b.get("total") == 0)

    # Create minimal contact
    r = requests.post(f"{BASE}/contacts", json={"full_name": "Minimal Contact"},
                     headers=auth_headers())
    test("Create minimal contact (name only)", r, 201,
         lambda b: b.get("full_name") == "Minimal Contact")

    # Missing full_name
    r = requests.post(f"{BASE}/contacts", json={"email": "no-name@test.com"},
                     headers=auth_headers())
    test("Reject contact without name → 400", r, 400)

    # Invalid alert status
    if ALERT_IDS:
        r = requests.patch(f"{BASE}/alerts/{ALERT_IDS[0]}",
                          json={"status": "invalid_status"}, headers=auth_headers())
        test("Reject invalid alert status → 400", r, 400)


# ═══════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════

def main():
    print(f"\n{BOLD}{'='*60}")
    print(f"  ContactIQ — Full API Test Suite")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}{RESET}")

    # Wait for server
    print(f"\n  Connecting to {BASE}...")
    for attempt in range(10):
        try:
            r = requests.get("http://127.0.0.1:5000/health", timeout=2)
            if r.status_code == 200:
                print(f"  {PASS} Server is running!")
                break
        except:
            pass
        time.sleep(0.5)
    else:
        print(f"  {FAIL} Server not responding. Start it with: python3 server.py")
        sys.exit(1)

    # Run all test groups
    test_health()
    test_auth()
    test_contacts()
    test_bulk_import()
    test_enrichment()
    test_monitoring()
    test_alerts()
    test_agent_tools()
    test_pagination_and_sorting()
    test_delete_contact()
    test_edge_cases()

    # Summary
    print(f"\n{BOLD}{'='*60}")
    print(f"  TEST RESULTS")
    print(f"{'='*60}{RESET}")
    print(f"  Total:  {results['total']}")
    print(f"  {PASS}:  {results['passed']}")
    if results["failed"] > 0:
        print(f"  {FAIL}:  {results['failed']}")
    else:
        print(f"  Failed: 0")
    pct = (results["passed"] / results["total"] * 100) if results["total"] > 0 else 0
    color = "\033[92m" if pct == 100 else "\033[93m" if pct >= 90 else "\033[91m"
    print(f"  Rate:   {color}{pct:.0f}%{RESET}")
    print(f"{'='*60}\n")

    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
