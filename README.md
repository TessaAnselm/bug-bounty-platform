# Bug Bounty Research Platform

A personal, structured platform for ethical bug bounty research. Built to support systematic vulnerability research across web applications, APIs, and AI-powered systems.

## Philosophy

Depth over breadth. Understanding targets well enough to find what automated tools miss — logic flaws, broken authorization, and chained vulnerabilities that require human reasoning.

## Approach

- Ethics-first — every engagement starts with a scope review and checklist
- Repeatable methodology applied consistently across targets
- Structured documentation of findings, hypotheses, and session notes
- Data-driven program selection based on ROI signals

## Stack

Built entirely on free and open source tools. Runs locally with no cloud dependencies.

- **Workflow orchestration:** Temporal OSS
- **Backend:** Python, FastAPI, PostgreSQL
- **AI interface:** Claude Code via local MCP server (read-only)
- **Security scanning:** Snyk, Semgrep, gitleaks

## Structure

```
core/               Universal methodology and templates
specializations/    Technique-specific research guides
docs/               Build and setup documentation
```

## Status

Active development. See [PROGRESS.md](PROGRESS.md) for current build status.

## Ethics

This project is built for authorized bug bounty programs only. All testing is conducted within explicitly defined program scope using dedicated test accounts. No real user data is accessed or stored.
