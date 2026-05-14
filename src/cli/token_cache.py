"""Token cache management for storing OIDC tokens on disk."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .keycloak_client import OIDCToken


class TokenCache:
    """File-based token cache for OIDC tokens."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        """Initialize token cache.

        Args:
            cache_dir: Directory for token cache files (default: ~/.itl/attestation-cache/)
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".itl" / "attestation-cache"
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, realm: str, client_id: str, username: str | None = None) -> str:
        """Generate cache key from realm, client_id and optional username.

        Args:
            realm: Keycloak realm
            client_id: OIDC client ID
            username: Optional username for user-specific cache

        Returns:
            MD5 hash of cache key components
        """
        key_parts = [realm, client_id]
        if username:
            key_parts.append(username)
        key = ":".join(key_parts)
        return hashlib.md5(key.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get cache file path for given cache key.

        Args:
            cache_key: MD5 hash cache key

        Returns:
            Path to cache file
        """
        return self.cache_dir / f"{cache_key}.json"

    def save(
        self,
        token: OIDCToken,
        realm: str,
        client_id: str,
        username: str | None = None,
    ) -> None:
        """Save token to cache.

        Args:
            token: OIDC token to cache
            realm: Keycloak realm
            client_id: OIDC client ID
            username: Optional username for user-specific cache
        """
        cache_key = self._get_cache_key(realm, client_id, username)
        cache_path = self._get_cache_path(cache_key)

        cache_data = {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "expires_at": token.expires_at.isoformat(),
            "token_type": token.token_type,
            "realm": realm,
            "client_id": client_id,
            "username": username,
        }

        cache_path.write_text(json.dumps(cache_data, indent=2))
        cache_path.chmod(0o600)  # Readable only by owner

    def load(
        self,
        realm: str,
        client_id: str,
        username: str | None = None,
    ) -> OIDCToken | None:
        """Load token from cache.

        Args:
            realm: Keycloak realm
            client_id: OIDC client ID
            username: Optional username for user-specific cache

        Returns:
            Cached token or None if not found/expired
        """
        cache_key = self._get_cache_key(realm, client_id, username)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            return None

        try:
            cache_data = json.loads(cache_path.read_text())
            token = OIDCToken(
                access_token=cache_data["access_token"],
                refresh_token=cache_data.get("refresh_token"),
                expires_at=datetime.fromisoformat(cache_data["expires_at"]),
                token_type=cache_data.get("token_type", "Bearer"),
            )

            # Don't return expired tokens
            if token.is_expired:
                return None

            return token
        except (json.JSONDecodeError, KeyError, ValueError):
            # Invalid cache file
            cache_path.unlink(missing_ok=True)
            return None

    def delete(
        self,
        realm: str,
        client_id: str,
        username: str | None = None,
    ) -> bool:
        """Delete token from cache.

        Args:
            realm: Keycloak realm
            client_id: OIDC client ID
            username: Optional username for user-specific cache

        Returns:
            True if token was deleted, False if not found
        """
        cache_key = self._get_cache_key(realm, client_id, username)
        cache_path = self._get_cache_path(cache_key)

        if cache_path.exists():
            cache_path.unlink()
            return True
        return False

    def list_cached_tokens(self) -> list[dict[str, Any]]:
        """List all cached tokens.

        Returns:
            List of token metadata dictionaries
        """
        tokens = []
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_data = json.loads(cache_file.read_text())
                expires_at = datetime.fromisoformat(cache_data["expires_at"])
                tokens.append(
                    {
                        "realm": cache_data.get("realm", "unknown"),
                        "client_id": cache_data.get("client_id", "unknown"),
                        "username": cache_data.get("username"),
                        "expires_at": expires_at,
                        "is_expired": expires_at <= datetime.now(timezone.utc),
                        "cache_file": cache_file.name,
                    }
                )
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return tokens

    def clear_all(self) -> int:
        """Delete all cached tokens.

        Returns:
            Number of tokens deleted
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        return count
