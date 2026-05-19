# IDOR + API Security Resources

## Must-Read

- **OWASP API Security Top 10** — https://owasp.org/www-project-api-security/
  The definitive reference for API vulnerability classes. Read the full list.

- **PortSwigger Web Academy — Access Control** — https://portswigger.net/web-security/access-control
  Free labs covering IDOR, privilege escalation, multi-step access control. Do every lab.

- **PortSwigger Web Academy — API Testing** — https://portswigger.net/web-security/api-testing
  Covers API recon, endpoint discovery, parameter testing.

## Disclosed Reports (Study These)

HackerOne disclosed reports are the best real-world learning material.

Search: https://hackerone.com/hacktivity?querystring=IDOR

Patterns to study:
- How did the researcher discover the vulnerable endpoint?
- What made the IDOR exploitable (sequential ID, UUID, indirect reference)?
- How was impact assessed and described?
- What was the fix?

## Books

- **The Web Application Hacker's Handbook** — Stuttard & Pinto
  Old but foundational. Chapter on access controls is still relevant.

- **Hacking APIs** — Corey Ball
  Modern, practical, covers REST and GraphQL testing in depth.

## Practice Labs

- **PortSwigger Web Academy** — https://portswigger.net/web-security (free)
- **PentesterLab** — https://pentesterlab.com (paid, worth it for API exercises)
- **HackTheBox** — https://hackthebox.com (machines with API attack paths)
- **DVWA** — Local lab for basic access control practice

## Cheat Sheets

- **IDOR Testing Cheat Sheet** — https://github.com/daffainfo/AllAboutBugBounty/blob/master/Insecure%20Direct%20Object%20References.md
- **API Security Checklist** — https://github.com/shieldfy/API-Security-Checklist

## YouTube / Walkthroughs

- NahamSec live recon sessions
- STÖK bug bounty content
- HackerOne YouTube channel — researcher spotlights with methodology breakdowns
