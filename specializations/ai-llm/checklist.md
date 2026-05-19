# AI/LLM Security Checklist

## Surface Mapping
- [ ] All AI-powered features identified and listed
- [ ] Input vectors mapped (chat, file upload, form fields, URL fetch)
- [ ] Available tools/functions identified (what can the LLM do?)
- [ ] Output rendering method identified (plain text, HTML, code execution)
- [ ] RAG usage identified (does the app ingest documents or external data?)

## Direct Prompt Injection
- [ ] Basic instruction override attempted ("ignore previous instructions")
- [ ] System prompt extraction attempted ("repeat your instructions")
- [ ] Role/persona override attempted
- [ ] Content filter bypass attempted
- [ ] Output format manipulation attempted (ask for JSON, code, etc.)

## Indirect Prompt Injection
- [ ] Injection via file upload tested (PDF, DOCX, TXT with embedded payloads)
- [ ] Injection via URL fetch tested (if app fetches external content)
- [ ] Injection via database-sourced content tested (if app reads user records into LLM context)
- [ ] Injection via email/ticket ingestion tested (if app processes external communications)

## Tool/Function Call Testing
- [ ] Available tools listed and documented
- [ ] Unauthorized tool invocation attempted via prompt
- [ ] Tool parameter manipulation via prompt injection tested
- [ ] Data exfiltration via permitted tool attempted (e.g., email, webhook)
- [ ] Chained tool calls tested for unintended behavior

## System Prompt Analysis
- [ ] Direct extraction attempted
- [ ] Partial extraction via completion attacks
- [ ] Credentials or sensitive data in system prompt checked
- [ ] Internal system references in system prompt noted

## RAG / Data Access
- [ ] Cross-user document access tested
- [ ] Query for system/admin documents attempted
- [ ] LLM asked to list accessible documents
- [ ] Injection via ingested document tested

## Output Handling
- [ ] LLM output rendered in browser — XSS via model response tested
- [ ] Code generation features — malicious code injection tested
- [ ] Markdown rendering — payload injection tested (`[text](javascript:alert(1))`)

## Authorization
- [ ] LLM-gated features tested for bypass via prompt
- [ ] Role-based access enforced at API layer (not only LLM layer)
- [ ] LLM decisions that affect data access verified server-side
