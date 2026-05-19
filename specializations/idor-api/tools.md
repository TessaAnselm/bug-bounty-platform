# IDOR + API Security Tools

## Core Tools

### Burp Suite Community
Primary proxy for capturing, modifying, and replaying requests.
- Use Repeater to manually test ID substitution
- Use Comparer to diff responses between accounts
- Use Logger to review all captured traffic
- Download: https://portswigger.net/burp

### Burp Autorize Extension
Automates IDOR testing by replaying every request with a different user's session.
- Install via BApp Store in Burp
- Set up victim session cookie, test with attacker session
- Flags responses that differ unexpectedly

### Postman / Insomnia
API clients for structured API testing.
- Useful for documenting and replaying API sequences
- Environment variables for switching between attacker/victim tokens

## Recon Tools (within scope only)

### httpx
Probe live hosts and fingerprint technologies.
```bash
echo "target.com" | httpx -title -tech-detect -status-code
```

### katana
Crawl web apps to surface endpoints and JS files.
```bash
katana -u https://target.com -d 3 -o endpoints.txt
```

### gau (GetAllUrls)
Pull historical URLs from Wayback Machine and other sources.
```bash
gau target.com | grep "api"
```

## API-Specific

### ffuf
Fuzz API endpoints for hidden paths (only where permitted by program).
```bash
ffuf -u https://api.target.com/FUZZ -w wordlists/api-endpoints.txt
```

### jwt_tool
Analyze and test JWT tokens for weaknesses (algorithm confusion, weak secrets).
```bash
python3 jwt_tool.py <token> -T
```

### GraphQL Voyager / InQL
Map GraphQL schemas and find exposed queries/mutations.

## Wordlists

- SecLists API wordlists: `Discovery/Web-Content/api/`
- Assetnote wordlists: https://wordlists.assetnote.io

## Note

Only run active scanning/fuzzing tools if the program policy explicitly permits it. When in doubt, test manually.
