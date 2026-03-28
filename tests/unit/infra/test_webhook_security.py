from __future__ import annotations

from api.security import compute_github_signature, verify_github_signature


def test_verify_github_signature_accepts_valid_signature():
    body = b'{"action":"opened"}'
    signature = compute_github_signature("secret", body)

    assert verify_github_signature("secret", signature, body) is True


def test_verify_github_signature_rejects_invalid_signature():
    body = b'{"action":"opened"}'

    assert verify_github_signature("secret", "sha256=deadbeef", body) is False
    assert verify_github_signature("secret", "", body) is False
    assert verify_github_signature("", "sha256=deadbeef", body) is False
