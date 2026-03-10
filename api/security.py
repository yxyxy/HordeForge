from __future__ import annotations

import hashlib
import hmac


def compute_github_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_github_signature(secret: str, signature_header: str, body: bytes) -> bool:
    if not secret or not signature_header:
        return False
    expected = compute_github_signature(secret, body)
    return hmac.compare_digest(expected, signature_header.strip())
