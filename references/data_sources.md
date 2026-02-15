# OSINT Data Sources

## Email Intelligence

### theHarvester
- **Purpose:** Email enumeration from public sources
- **Sources:** Google, Bing, LinkedIn, Twitter, DNSdumpster, etc.
- **Usage:** `theHarvester -d domain.com -b all`
- **Output:** Emails, subdomains, IPs, URLs

### holehe
- **Purpose:** Check email registration on 120+ platforms
- **Platforms:** Social media, gaming, dating, shopping sites
- **Usage:** `holehe email@example.com`
- **Output:** Platform registration status

### hunter.io
- **Purpose:** Email finder and verifier
- **API:** Available (requires key)
- **Web:** https://hunter.io

## Username Intelligence

### sherlock
- **Purpose:** Hunt username across 300+ social networks
- **Platforms:** Twitter, Instagram, GitHub, Reddit, LinkedIn, etc.
- **Usage:** `sherlock username --timeout 10`
- **Output:** Profile URLs, existence status

### whatsmyname
- **Purpose:** Username enumeration
- **Web:** https://whatsmyname.app

## Phone Intelligence

### phoneinfoga
- **Purpose:** Phone number OSINT scanner
- **Features:** Carrier lookup, location, social media links
- **Usage:** `phoneinfoga scan -n +1234567890`

### truecaller
- **Web:** https://www.truecaller.com
- **Note:** Requires account

## Domain Intelligence

### subfinder
- **Purpose:** Passive subdomain enumeration
- **Sources:** 30+ passive sources
- **Usage:** `subfinder -d domain.com`
- **Fast:** ~10-30 seconds per domain

### amass
- **Purpose:** In-depth subdomain enumeration
- **Features:** DNS, scraping, brute-force, APIs
- **Usage:** `amass enum -d domain.com`
- **Slow:** ~5-15 minutes per domain

### WHOIS
- **Purpose:** Domain registration info
- **Data:** Registrar, dates, nameservers
- **Usage:** `whois domain.com`

### DNS Records
- **Types:** A, MX, TXT, NS, CNAME, SOA
- **Tools:** dig, nslookup, dnsenum
- **Usage:** `dig domain.com ANY`

## Social Media OSINT

### LinkedIn
- **Tools:** theHarvester, PhantomBuster
- **Data:** Employees, job titles, company structure
- **Web:** https://linkedin.com

### GitHub
- **Search:** Code, commits, gists, users
- **Tools:** GitHub API, ghunt, gitrob
- **Web:** https://github.com

### Twitter/X
- **Tools:** Twint (deprecated), Twitter API
- **Data:** Tweets, followers, location
- **Web:** https://twitter.com

## Public Records

### Search Engines
- **Google Dorks:** Advanced search operators
- **Bing, DuckDuckGo:** Alternative indexes
- **Examples:** 
  - `site:linkedin.com "company name"`
  - `inurl:admin site:target.com`

### Archives
- **Wayback Machine:** https://web.archive.org
- **Archive.is:** https://archive.is

### Data Breach Databases
- **Have I Been Pwned:** https://haveibeenpwned.com
- **DeHashed:** https://dehashed.com (paid)
- **LeakCheck:** https://leakcheck.io

## Metadata Extraction

### exiftool
- **Purpose:** Extract metadata from files
- **Files:** Images, PDFs, Office docs
- **Usage:** `exiftool photo.jpg`

## Network Intelligence

### Shodan
- **Purpose:** Internet-connected device search
- **Web:** https://shodan.io
- **API:** Available (requires key)

### Censys
- **Purpose:** Internet-wide scan data
- **Web:** https://censys.io

## OSINT Frameworks

### Maltego
- **Purpose:** Visual link analysis
- **Type:** Desktop application
- **License:** Community (limited) / Pro

### SpiderFoot
- **Purpose:** Automated OSINT collection
- **Type:** Web application
- **Open Source:** Yes
