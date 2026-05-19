# AI/LLM Security Resources

## Foundational

- **OWASP Top 10 for LLM Applications**
  https://owasp.org/www-project-top-10-for-large-language-model-applications/
  The definitive reference. Read every entry. This is what programs use to evaluate AI-related reports.

- **OWASP LLM AI Security & Governance Checklist**
  https://owasp.org/www-project-top-10-for-large-language-model-applications/

## Research Papers

- **Prompt Injection Attacks against LLM-Integrated Applications**
  https://arxiv.org/abs/2302.12173
  Original academic paper on indirect prompt injection.

- **Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications**
  https://arxiv.org/abs/2302.12173
  Real-world examples of LLM application compromises.

## Practical Guides

- **Embracing the Red Team: Prompt Injection** — Simon Willison's blog
  https://simonwillison.net/tags/prompt-injection/
  Best ongoing coverage of real prompt injection cases.

- **Attacking LLM Applications** — Snyk / various security researchers
  Search for recent blog posts — this space moves fast.

## Disclosed Reports

Bug bounty programs with AI features are increasingly disclosing LLM-related reports:
- Search HackerOne: https://hackerone.com/hacktivity?querystring=prompt+injection
- Search HackerOne: https://hackerone.com/hacktivity?querystring=LLM

## Anthropic's Security Research

- **Anthropic Red Team / red.anthropic.com**
  https://red.anthropic.com
  Anthropic publishes their own AI safety and security research here.

- **Claude Usage Policy**
  https://www.anthropic.com/legal/usage-policy
  Understanding what behaviors Anthropic considers policy violations vs security vulnerabilities.

## Practice

- **Gandalf by Lakera** — https://gandalf.lakera.ai
  Gamified prompt injection challenges. Good for developing intuition.

- **Prompt Airlines** — https://promptairlines.com
  Prompt injection CTF-style challenges.

- **HackAPrompt** — https://huggingface.co/datasets/hackaprompt/hackaprompt-dataset
  Dataset of prompt injection attempts — study patterns.

## Communities

- **AI Village** — https://aivillage.org
  Security researchers focused on AI/ML. DEF CON AI Village talks are excellent.

- **MLSecOps Community** — https://mlsecops.com

## Staying Current

This field moves faster than any other in bug bounty. Follow:
- Simon Willison (simonwillison.net) — best prompt injection coverage
- Joseph Thacker (@rez0__) — AI security bug bounty research
- Johann Rehberger (@wunderwuzzi23) — indirect prompt injection research
