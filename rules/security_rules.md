# Security Rules

## Secrets

- Never log plaintext credentials, tokens, or webhook secrets.
- Use existing redaction helpers for structured logs and persisted payloads.

## Validation

- Reject invalid signatures and malformed external payloads early.
- Validate command authorization before executing privileged actions.

## Safe Defaults

- Keep strict validation enabled unless there is a documented exception.
- Fail closed when permissions or identity claims are missing.
