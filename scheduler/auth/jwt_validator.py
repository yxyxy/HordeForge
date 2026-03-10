"""JWT validation and decoding (HF-P7-002)."""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import jwt

logger = logging.getLogger(__name__)


@dataclass
class JWTPayload:
    """JWT token payload."""

    subject: str
    email: str | None = None
    roles: list[str] | None = None
    expires_at: int | None = None
    issued_at: int | None = None
    issuer: str | None = None
    audience: str | None = None
    extra: dict[str, Any] | None = None


class JWTValidator:
    """JWT token validator."""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        issuer: str | None = None,
        audience: str | None = None,
    ) -> None:
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.issuer = issuer
        self.audience = audience

    def create_token(
        self,
        subject: str,
        email: str | None = None,
        roles: list[str] | None = None,
        expires_in: int = 3600,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        """Create a JWT token.

        Args:
            subject: User identifier
            email: User email
            roles: User roles
            expires_in: Token expiration in seconds
            extra_claims: Additional claims

        Returns:
            Encoded JWT token
        """
        now = int(time.time())
        payload = {
            "sub": subject,
            "iat": now,
            "exp": now + expires_in,
        }

        if email:
            payload["email"] = email
        if roles:
            payload["roles"] = roles
        if self.issuer:
            payload["iss"] = self.issuer
        if self.audience:
            payload["aud"] = self.audience
        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def validate_token(self, token: str) -> JWTPayload | None:
        """Validate a JWT token.

        Args:
            token: JWT token string

        Returns:
            JWTPayload if valid, None if invalid
        """
        try:
            payload = self._decode_token(token)
            return self._parse_payload(payload)
        except jwt.ExpiredSignatureError:
            logger.debug("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.debug("JWT token invalid: %s", e)
            return None
        except Exception as e:
            logger.error("JWT validation error: %s", e)
            return None

    def _decode_token(self, token: str) -> dict[str, Any]:
        """Decode JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded payload

        Raises:
            jwt.InvalidTokenError: If token is invalid
        """
        return jwt.decode(
            token,
            self.secret_key,
            algorithms=[self.algorithm],
            issuer=self.issuer,
            audience=self.audience,
        )

    def _parse_payload(self, payload: dict[str, Any]) -> JWTPayload:
        """Parse JWT payload into JWTPayload.

        Args:
            payload: Decoded JWT payload

        Returns:
            JWTPayload instance
        """
        extra = dict(payload)
        for key in ["sub", "email", "roles", "exp", "iat", "iss", "aud"]:
            extra.pop(key, None)

        return JWTPayload(
            subject=payload.get("sub", ""),
            email=payload.get("email"),
            roles=payload.get("roles"),
            expires_at=payload.get("exp"),
            issued_at=payload.get("iat"),
            issuer=payload.get("iss"),
            audience=payload.get("aud"),
            extra=extra if extra else None,
        )

    def refresh_token(self, token: str, expires_in: int = 3600) -> str | None:
        """Refresh an existing token.

        Args:
            token: Current JWT token
            expires_in: New expiration in seconds

        Returns:
            New JWT token or None if invalid
        """
        payload = self.validate_token(token)
        if payload is None:
            return None

        return self.create_token(
            subject=payload.subject,
            email=payload.email,
            roles=payload.roles,
            expires_in=expires_in,
            extra_claims=payload.extra,
        )


def decode_jwt_payload(encoded_payload: str) -> dict[str, Any]:
    """Decode JWT payload from base64url encoding.

    This is a low-level function that only decodes the payload
    without validation. Use JWTValidator for full validation.

    Args:
        encoded_payload: Base64url encoded payload

    Returns:
        Decoded payload dictionary
    """
    # Add padding if needed
    padding = 4 - (len(encoded_payload) % 4)
    if padding != 4:
        encoded_payload += "=" * padding

    decoded = base64.urlsafe_b64decode(encoded_payload)
    return json.loads(decoded)


def validate_jwt_token(
    token: str,
    secret_key: str,
    algorithm: str = "HS256",
    issuer: str | None = None,
    audience: str | None = None,
) -> JWTPayload | None:
    """Convenience function to validate a JWT token.

    Args:
        token: JWT token string
        secret_key: Secret key for validation
        algorithm: Algorithm (HS256, RS256, etc.)
        issuer: Expected issuer
        audience: Expected audience

    Returns:
        JWTPayload if valid, None if invalid
    """
    validator = JWTValidator(
        secret_key=secret_key,
        algorithm=algorithm,
        issuer=issuer,
        audience=audience,
    )
    return validator.validate_token(token)
