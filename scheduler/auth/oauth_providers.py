"""OAuth/OIDC providers for authentication (HF-P7-002)."""

from __future__ import annotations

import logging
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)


@dataclass
class OAuthUserInfo:
    """OAuth user information."""

    user_id: str
    email: str
    name: str | None = None
    avatar_url: str | None = None
    provider: str = "unknown"


class OAuthProvider(ABC):
    """Abstract base class for OAuth providers."""

    @abstractmethod
    def get_authorization_url(self, state: str) -> str:
        """Get OAuth authorization URL.

        Args:
            state: Random state string for CSRF protection

        Returns:
            Authorization URL to redirect user to
        """
        pass

    @abstractmethod
    def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from callback

        Returns:
            Token response with access_token and optionally id_token
        """
        pass

    @abstractmethod
    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user information using access token.

        Args:
            access_token: OAuth access token

        Returns:
            OAuthUserInfo with user details
        """
        pass


class GoogleOAuthProvider(OAuthProvider):
    """Google OAuth 2.0 provider."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or [
            "openid",
            "email",
            "profile",
        ]
        self.auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_url = "https://oauth2.googleapis.com/token"
        self.userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"

    def get_authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.auth_url}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }
        response = requests.post(self.token_url, data=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(self.userinfo_url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        return OAuthUserInfo(
            user_id=data.get("sub", ""),
            email=data.get("email", ""),
            name=data.get("name"),
            avatar_url=data.get("picture"),
            provider="google",
        )


class GitHubOAuthProvider(OAuthProvider):
    """GitHub OAuth provider."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or ["read:user", "user:email"]
        self.auth_url = "https://github.com/login/oauth/authorize"
        self.token_url = "https://github.com/login/oauth/access_token"
        self.userinfo_url = "https://api.github.com/user"

    def get_authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": ",".join(self.scopes),
            "state": state,
        }
        return f"{self.auth_url}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
        }
        headers = {"Accept": "application/json"}
        response = requests.post(
            self.token_url,
            data=data,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        response = requests.get(self.userinfo_url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Get primary email if not in user info
        email = data.get("email")
        if not email:
            email_response = requests.get(
                "https://api.github.com/user/emails",
                headers=headers,
                timeout=30,
            )
            if email_response.status_code == 200:
                emails = email_response.json()
                primary = next((e for e in emails if e.get("primary")), None)
                if primary:
                    email = primary.get("email", "")

        return OAuthUserInfo(
            user_id=str(data.get("id", "")),
            email=email or "",
            name=data.get("name"),
            avatar_url=data.get("avatar_url"),
            provider="github",
        )


class OIDCOAuthProvider(OAuthProvider):
    """Generic OIDC provider."""

    def __init__(
        self,
        issuer_url: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> None:
        self.issuer_url = issuer_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or ["openid", "email", "profile"]

        # Discover OIDC configuration
        self._discover_config()

    def _discover_config(self) -> None:
        """Discover OIDC configuration from issuer."""
        try:
            discover_url = f"{self.issuer_url}/.well-known/openid-configuration"
            response = requests.get(discover_url, timeout=30)
            response.raise_for_status()
            config = response.json()

            self.auth_url = config.get("authorization_endpoint", "")
            self.token_url = config.get("token_endpoint", "")
            self.userinfo_url = config.get("userinfo_endpoint", "")
            self.jwks_uri = config.get("jwks_uri", "")

            logger.info("OIDC config discovered for %s", self.issuer_url)
        except Exception as e:
            logger.warning("Failed to discover OIDC config: %s", e)
            # Set default paths
            self.auth_url = f"{self.issuer_url}/authorize"
            self.token_url = f"{self.issuer_url}/token"
            self.userinfo_url = f"{self.issuer_url}/userinfo"
            self.jwks_uri = f"{self.issuer_url}/.well-known/jwks.json"

    def get_authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
        }
        return f"{self.auth_url}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }
        response = requests.post(self.token_url, data=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(self.userinfo_url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        return OAuthUserInfo(
            user_id=data.get("sub", ""),
            email=data.get("email", ""),
            name=data.get("name"),
            avatar_url=data.get("picture"),
            provider="oidc",
        )


def get_oauth_provider(
    provider: str,
    **kwargs: Any,
) -> OAuthProvider:
    """Factory function to get OAuth provider.

    Args:
        provider: Provider name ("google", "github", "oidc")
        **kwargs: Provider-specific configuration

    Returns:
        OAuthProvider instance

    Raises:
        ValueError: If provider is not supported
    """
    provider_lower = provider.lower()

    if provider_lower == "google":
        return GoogleOAuthProvider(**kwargs)
    elif provider_lower == "github":
        return GitHubOAuthProvider(**kwargs)
    elif provider_lower == "oidc":
        return OIDCOAuthProvider(**kwargs)
    else:
        raise ValueError(f"Unsupported OAuth provider: {provider}")
