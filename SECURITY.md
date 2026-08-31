# Security Policy

FinContract AI handles contract documents and may process personally identifiable information.
The project is a proof of concept, not a production legal service.

## Reporting a vulnerability

Do not include document contents, personal information, API keys, exploit payloads, or other
sensitive details in a public issue.

Use GitHub's private vulnerability reporting channel:

- <https://github.com/jangyoungdo/fincontract-ai/security/advisories/new>

If private reporting is unavailable, open a public issue containing only a request for a private
contact channel. Do not disclose the vulnerability details until a private channel is available.

## Supported versions

Only the latest commit on `main` is considered for security fixes. No released production version
is currently supported.

## Sensitive-data policy

- Never commit real contracts, extracted document text, API keys, `.env` files, databases, vector
  indexes, uploads, reports, or encryption keys.
- Tests and demonstrations must use synthetic or explicitly redistributable public data.
- Unmasked document text must not be sent to ChromaDB, external LLM providers, logs, or analytics.
- Suspected data exposure requires key rotation, removal of the exposed artifact, Git history review,
  and an audit of downstream caches before normal operation resumes.

## Security boundaries

The repository includes privacy and failure-safety controls, but the following remain outside the
current verified boundary:

- production KMS integration and encryption-key rotation;
- production Claude account retention and regional-processing verification;
- OCR security and quality validation for scanned documents;
- complete container and network-failure testing;
- independent legal and security review.
