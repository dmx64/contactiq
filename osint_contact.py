#!/usr/bin/env python3
"""
Contact OSINT Tool - Gather publicly available information about contacts
Supports: email, username, phone, domain
"""

import subprocess
import json
import sys
import os
from pathlib import Path

def run_command(cmd, timeout=60):
    """Run shell command and return output"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, 
            text=True, timeout=timeout
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Timeout after {timeout}s", 1

def email_osint(email):
    """Gather OSINT on email address"""
    results = {"email": email, "sources": {}}
    
    # theHarvester - email enumeration
    print(f"[*] Running theHarvester for {email}...")
    domain = email.split("@")[1] if "@" in email else email
    stdout, stderr, code = run_command(
        f"theHarvester -d {domain} -b all -f /tmp/harvest_{domain}.json 2>&1",
        timeout=120
    )
    if code == 0:
        results["sources"]["theHarvester"] = "completed"
    else:
        results["sources"]["theHarvester"] = f"error: {stderr[:200]}"
    
    # holehe - check email on social platforms
    holehe_path = subprocess.run("which holehe", shell=True, capture_output=True, text=True)
    if holehe_path.returncode == 0:
        print(f"[*] Running holehe for {email}...")
        stdout, stderr, code = run_command(f"holehe {email} 2>&1", timeout=60)
        if code == 0:
            results["sources"]["holehe"] = stdout
        else:
            results["sources"]["holehe"] = f"error: {stderr[:200]}"
    
    return results

def username_osint(username):
    """Gather OSINT on username"""
    results = {"username": username, "sources": {}}
    
    # sherlock - find username across social networks
    print(f"[*] Running sherlock for {username}...")
    stdout, stderr, code = run_command(
        f"sherlock {username} --timeout 10 --json --output /tmp/sherlock_{username}.json 2>&1",
        timeout=120
    )
    if code == 0:
        results["sources"]["sherlock"] = "completed"
        try:
            with open(f"/tmp/sherlock_{username}.json", "r") as f:
                sherlock_data = json.load(f)
                results["found_on"] = list(sherlock_data.keys())
        except:
            pass
    else:
        results["sources"]["sherlock"] = f"error: {stderr[:200]}"
    
    return results

def phone_osint(phone):
    """Gather OSINT on phone number"""
    results = {"phone": phone, "sources": {}}
    
    # Basic phone validation and format
    clean_phone = ''.join(filter(str.isdigit, phone))
    results["clean_phone"] = clean_phone
    
    # PhoneInfoga (if installed)
    phoneinfoga_path = subprocess.run("which phoneinfoga", shell=True, capture_output=True, text=True)
    if phoneinfoga_path.returncode == 0:
        print(f"[*] Running phoneinfoga for {phone}...")
        stdout, stderr, code = run_command(f"phoneinfoga scan -n {clean_phone} 2>&1", timeout=60)
        if code == 0:
            results["sources"]["phoneinfoga"] = stdout
    
    results["sources"]["note"] = "Phone OSINT limited - use specialized services for deeper research"
    
    return results

def domain_osint(domain):
    """Gather OSINT on domain"""
    results = {"domain": domain, "sources": {}}
    
    # WHOIS lookup
    print(f"[*] Running WHOIS for {domain}...")
    stdout, stderr, code = run_command(f"whois {domain} 2>&1", timeout=30)
    if code == 0:
        results["sources"]["whois"] = stdout[:1000]  # truncate
    
    # subfinder - subdomain enumeration
    print(f"[*] Running subfinder for {domain}...")
    stdout, stderr, code = run_command(
        f"~/go/bin/subfinder -d {domain} -silent -timeout 60 2>&1",
        timeout=90
    )
    if code == 0:
        subdomains = stdout.strip().split('\n')
        results["subdomains"] = subdomains[:50]  # limit to 50
        results["subdomain_count"] = len(subdomains)
    
    # DNS records
    print(f"[*] Getting DNS records for {domain}...")
    for record_type in ["A", "MX", "TXT", "NS"]:
        stdout, stderr, code = run_command(f"dig {domain} {record_type} +short 2>&1", timeout=10)
        if code == 0 and stdout.strip():
            results[f"dns_{record_type.lower()}"] = stdout.strip().split('\n')
    
    return results

def main():
    if len(sys.argv) < 3:
        print("Usage: osint_contact.py <type> <value>")
        print("Types: email, username, phone, domain")
        print("\nExamples:")
        print("  osint_contact.py email john@example.com")
        print("  osint_contact.py username johndoe")
        print("  osint_contact.py phone +1234567890")
        print("  osint_contact.py domain example.com")
        sys.exit(1)
    
    osint_type = sys.argv[1].lower()
    value = sys.argv[2]
    
    print(f"[OSINT] Starting {osint_type} OSINT for: {value}")
    print("-" * 60)
    
    if osint_type == "email":
        results = email_osint(value)
    elif osint_type == "username":
        results = username_osint(value)
    elif osint_type == "phone":
        results = phone_osint(value)
    elif osint_type == "domain":
        results = domain_osint(value)
    else:
        print(f"Error: Unknown type '{osint_type}'")
        sys.exit(1)
    
    # Output results
    print("\n" + "=" * 60)
    print("RESULTS:")
    print("=" * 60)
    print(json.dumps(results, indent=2))
    
    # Save to file
    output_file = f"/tmp/osint_{osint_type}_{value.replace('@', '_at_').replace('.', '_')}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[OK] Results saved to: {output_file}")

if __name__ == "__main__":
    main()
