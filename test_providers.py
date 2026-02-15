"""
ContactIQ — Real Providers Test
Tests each provider individually, then runs full pipeline.
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from providers import (
    GoogleNewsRSS, GitHubAPI, WikidataAPI, GravatarAPI, ClearbitLogo,
    GNewsAPI, GuardianAPI, SECEDGAR, OpenCorporatesAPI, OpenSanctionsAPI,
    MailcheckAPI, EnrichmentPipeline, ALL_PROVIDERS,
)

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
MOCK = "\033[93m⚡\033[0m"
H = "\033[96m"
B = "\033[1m"
R = "\033[0m"
DIM = "\033[90m"

stats = {"pass": 0, "mock": 0, "fail": 0}


def show_result(name, result, key_fields=None):
    """Display provider result."""
    status = result.get("status", "unknown")
    
    if status == "success":
        icon = PASS
        stats["pass"] += 1
        label = "\033[92mLIVE\033[0m"
    elif status in ("mock", "partial"):
        icon = MOCK
        stats["mock"] += 1
        label = "\033[93mMOCK\033[0m"
    else:
        icon = FAIL
        stats["fail"] += 1
        label = "\033[91mFAIL\033[0m"

    print(f"  {icon} {name:<28} [{label}]", end="")
    
    if result.get("confidence"):
        print(f"  conf={result['confidence']:.0%}", end="")
    
    # Show key data
    data = result.get("data") or result.get("items")
    if key_fields and isinstance(data, dict):
        shown = []
        for f in key_fields:
            v = data.get(f)
            if v and v is not None:
                if isinstance(v, str) and len(v) > 40:
                    v = v[:37] + "..."
                shown.append(f"{f}={v}")
        if shown:
            print(f"  {DIM}{' · '.join(shown[:3])}{R}", end="")
    elif isinstance(data, list) and data:
        count = len(data)
        first = data[0] if data else {}
        if isinstance(first, dict):
            title = first.get("title", first.get("name", ""))[:50]
            print(f"  {DIM}{count} items · \"{title}\"{R}", end="")
    
    print()
    
    if status in ("error",) and result.get("error"):
        print(f"       {DIM}Error: {result['error'][:80]}{R}")

    return result


def section(title):
    print(f"\n{H}{'─'*60}")
    print(f"  {B}{title}")
    print(f"{'─'*60}{R}")


def main():
    print(f"\n{B}{'═'*60}")
    print(f"  ContactIQ — Real Providers Test Suite")
    print(f"  Testing {len(ALL_PROVIDERS)} data providers")
    print(f"{'═'*60}{R}")

    # ═══ Test contacts ═══
    contacts = [
        {"full_name": "Elon Musk", "email": "elon@tesla.com", "company": "Tesla"},
        {"full_name": "Satya Nadella", "email": "satya@microsoft.com", "company": "Microsoft"},
        {"full_name": "Dario Amodei", "email": "dario@anthropic.com", "company": "Anthropic"},
    ]

    # ─── Individual Provider Tests ───

    section("1. GOOGLE NEWS RSS (unlimited, no key)")
    for c in contacts[:2]:
        r = GoogleNewsRSS.search(c["full_name"], max_results=3)
        show_result(f"News: {c['full_name']}", r)

    section("2. GITHUB API (5000/hr with token)")
    for c in contacts:
        r = GitHubAPI.search_user(c["full_name"])
        show_result(f"GitHub: {c['full_name']}", r, ["github_username", "company", "location"])
    
    # Test by email
    r = GitHubAPI.enrich_by_email("torvalds@linux-foundation.org")
    show_result("GitHub by email: torvalds", r, ["github_username", "followers"])

    section("3. WIKIDATA (unlimited, no key)")
    for c in contacts[:2]:
        r = WikidataAPI.search_person(c["full_name"])
        show_result(f"Wikidata: {c['full_name']}", r, ["occupation", "employer", "nationality", "wikipedia_url"])

    section("4. GRAVATAR (unlimited, no key)")
    for c in contacts:
        if c.get("email"):
            r = GravatarAPI.lookup(c["email"])
            show_result(f"Gravatar: {c['email']}", r, ["avatar_url", "display_name"])

    section("5. CLEARBIT LOGO (unlimited, no key)")
    for company in ["Tesla", "Microsoft", "Anthropic", "Google"]:
        r = ClearbitLogo.get_logo_url(company)
        show_result(f"Logo: {company}", r, ["logo_url"])

    section("6. OPENCORPORATES (free for research)")
    r = OpenCorporatesAPI.search_company("Tesla")
    show_result("Company: Tesla", r)
    
    r = OpenCorporatesAPI.search_officer("Elon Musk")
    show_result("Officer: Elon Musk", r)

    section("7. SEC EDGAR (free, US public companies)")
    r = SECEDGAR.search_company("Tesla")
    show_result("SEC: Tesla", r)

    section("8. OPENSANCTIONS (free bulk, self-host free)")
    for name in ["Elon Musk", "Vladimir Putin"]:
        r = OpenSanctionsAPI.match_person(name)
        data = r.get("data", {})
        extra = f"  sanctioned={data.get('is_sanctioned')} pep={data.get('is_pep')} risk={data.get('risk_score')}"
        show_result(f"Sanctions: {name}", r)
        print(f"       {DIM}{extra}{R}")

    section("9. MAILCHECK (free, unlimited)")
    for email in ["elon@tesla.com", "test@mailinator.com", "invalid-email"]:
        r = MailcheckAPI.validate(email)
        show_result(f"Email: {email}", r, ["valid_format", "disposable"])

    section("10. GNEWS & GUARDIAN (need API keys)")
    r = GNewsAPI.search("Tesla", api_key=None)
    show_result("GNews (no key)", r)
    r = GuardianAPI.search("Tesla", api_key=None)
    show_result("Guardian (no key)", r)
    print(f"  {DIM}→ Get free GNews key: https://gnews.io{R}")
    print(f"  {DIM}→ Get free Guardian key: https://open-platform.theguardian.com/access/{R}")

    # ─── Full Pipeline Test ───

    section("FULL ENRICHMENT PIPELINE")
    pipeline = EnrichmentPipeline()

    for c in contacts:
        print(f"\n  {B}▶ Enriching: {c['full_name']}{R}")
        result = pipeline.enrich_contact(c)
        
        print(f"    Score: {B}{result['enrichment_score']}%{R}")
        print(f"    Providers: {result['providers_used']}")
        print(f"    Cost: ${result['total_cost_usd']:.4f}")
        
        merged = result.get("merged_profile", {})
        print(f"    {DIM}Data found:{R}")
        for k, v in merged.items():
            if v is not None and k not in ("corporate_roles", "sanctions_check"):
                val = str(v)
                if len(val) > 60:
                    val = val[:57] + "..."
                print(f"      {k}: {val}")
        
        if merged.get("sanctions_check"):
            sc = merged["sanctions_check"]
            color = "\033[91m" if sc.get("is_sanctioned") else "\033[92m"
            print(f"      sanctions: {color}sanctioned={sc.get('is_sanctioned')} pep={sc.get('is_pep')} risk={sc.get('risk_score')}{R}")
        
        if merged.get("corporate_roles"):
            roles = merged["corporate_roles"][:3]
            for role in roles:
                if isinstance(role, dict):
                    print(f"      role: {role.get('position', '?')} @ {role.get('company_name', '?')}")

    # ─── Monitoring Pipeline Test ───

    section("NEWS MONITORING PIPELINE")
    for c in contacts[:2]:
        print(f"\n  {B}▶ Scanning news: {c['full_name']}{R}")
        result = pipeline.monitor_contact(c)
        
        print(f"    Items found: {result['total_items']}")
        print(f"    Sources: {result['sources_used']}")
        
        for item in result.get("items", [])[:3]:
            title = item.get("title", "")[:60]
            source = item.get("source", "?")
            print(f"    {DIM}→ [{source}] {title}{R}")

    # ─── Summary ───

    total = stats["pass"] + stats["mock"] + stats["fail"]
    print(f"\n{B}{'═'*60}")
    print(f"  RESULTS")
    print(f"{'═'*60}{R}")
    print(f"  Total tests:   {total}")
    print(f"  {PASS} Live API:    {stats['pass']}")
    print(f"  {MOCK} Mock/Fallback: {stats['mock']}")
    print(f"  {FAIL} Failed:      {stats['fail']}")
    
    if stats["mock"] > 0:
        print(f"\n  {DIM}⚡ Mock results = network unavailable in sandbox")
        print(f"     Deploy with network access → all providers go LIVE{R}")
    
    print(f"\n  {B}Provider Summary:{R}")
    for name, info in ALL_PROVIDERS.items():
        key_icon = "🔑" if info["key"] else "🆓"
        print(f"    {key_icon} {name:<22} [{info['category']}] {info['cost']}")

    print(f"\n  {B}Free API Keys to get:{R}")
    print(f"    1. GNews:          https://gnews.io (100 req/day)")
    print(f"    2. Guardian:       https://open-platform.theguardian.com/access/ (5000/day)")
    print(f"    3. Apollo.io:      https://app.apollo.io (100 credits/mo)")
    print(f"    4. OpenCorporates: https://opencorporates.com/api_accounts/new (research)")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
