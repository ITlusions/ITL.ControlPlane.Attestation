"""OIDC authentication client for Keycloak.

Supports multiple authentication flows:
- Interactive browser-based (PKCE)
- Command-line (username/password)
- Device code flow (for headless environments)
"""
from __future__ import annotations

import hashlib
import secrets
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode, urljoin

import httpx


@dataclass
class OIDCToken:
    """OIDC token response."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime
    token_type: str = "Bearer"

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 5 min buffer)."""
        return datetime.now(timezone.utc) >= self.expires_at - timedelta(minutes=5)

    @property
    def authorization_header(self) -> str:
        """Get Authorization header value."""
        return f"{self.token_type} {self.access_token}"


class KeycloakClient:
    """Keycloak OIDC client supporting multiple authentication flows."""

    def __init__(
        self,
        keycloak_url: str,
        realm: str,
        client_id: str,
        client_secret: str | None = None,
    ) -> None:
        """Initialize Keycloak client.

        Args:
            keycloak_url: Keycloak base URL (e.g. https://sts.itlusions.com)
            realm: Realm name (e.g. itlusions)
            client_id: Client ID (e.g. attestation-cli)
            client_secret: Optional client secret (for confidential clients)
        """
        self.keycloak_url = keycloak_url.rstrip("/")
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.realm_url = f"{self.keycloak_url}/realms/{realm}"
        self.token_endpoint = f"{self.realm_url}/protocol/openid-connect/token"
        self.auth_endpoint = f"{self.realm_url}/protocol/openid-connect/auth"
        self.device_endpoint = f"{self.realm_url}/protocol/openid-connect/auth/device"

    def login_interactive(self, redirect_port: int = 8765) -> OIDCToken:
        """Interactive browser-based login with PKCE flow.

        Args:
            redirect_port: Local port for redirect URI (default: 8765)

        Returns:
            OIDCToken with access token and refresh token

        Raises:
            RuntimeError: If authentication fails
        """
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from urllib.parse import parse_qs, urlparse

        # Generate PKCE challenge
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            hashlib.sha256(code_verifier.encode()).digest().hex()
        )

        redirect_uri = f"http://localhost:{redirect_port}/callback"
        state = secrets.token_urlsafe(32)

        # Build authorization URL
        auth_params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        auth_url = f"{self.auth_endpoint}?{urlencode(auth_params)}"

        # Store authorization code
        auth_code_holder: dict[str, str] = {}

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                query = parse_qs(urlparse(self.path).query)
                if "code" in query:
                    auth_code_holder["code"] = query["code"][0]
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(
                        b"<h1>Authentication successful!</h1><p>You can close this window.</p>"
                    )
                else:
                    self.send_response(400)
                    self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:
                pass  # Suppress logs

        # Start local server
        server = HTTPServer(("localhost", redirect_port), CallbackHandler)
        print(f"🌐 Opening browser for authentication...")
        print(f"   If browser doesn't open, visit: {auth_url}")
        webbrowser.open(auth_url)

        # Wait for callback
        server.handle_request()
        server.server_close()

        if "code" not in auth_code_holder:
            raise RuntimeError("Authentication failed: no authorization code received")

        # Exchange code for token
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code_holder["code"],
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "code_verifier": code_verifier,
        }
        if self.client_secret:
            token_data["client_secret"] = self.client_secret

        response = httpx.post(self.token_endpoint, data=token_data, timeout=30.0)
        response.raise_for_status()
        token_json = response.json()

        return OIDCToken(
            access_token=token_json["access_token"],
            refresh_token=token_json.get("refresh_token"),
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=token_json["expires_in"]),
        )

    def login_password(self, username: str, password: str) -> OIDCToken:
        """Command-line password-based login (Resource Owner Password Credentials).

        Args:
            username: Username or email
            password: Password

        Returns:
            OIDCToken with access token and refresh token

        Raises:
            httpx.HTTPStatusError: If authentication fails
        """
        token_data = {
            "grant_type": "password",
            "client_id": self.client_id,
            "username": username,
            "password": password,
            "scope": "openid profile email",
        }
        if self.client_secret:
            token_data["client_secret"] = self.client_secret

        response = httpx.post(self.token_endpoint, data=token_data, timeout=30.0)
        response.raise_for_status()
        token_json = response.json()

        return OIDCToken(
            access_token=token_json["access_token"],
            refresh_token=token_json.get("refresh_token"),
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=token_json["expires_in"]),
        )

    def login_device_code(self) -> OIDCToken:
        """Device code flow for headless environments.

        Returns:
            OIDCToken with access token and refresh token

        Raises:
            RuntimeError: If authentication fails or times out
        """
        import time

        # Request device code
        device_data = {
            "client_id": self.client_id,
        }
        if self.client_secret:
            device_data["client_secret"] = self.client_secret

        response = httpx.post(self.device_endpoint, data=device_data, timeout=30.0)
        response.raise_for_status()
        device_json = response.json()

        device_code = device_json["device_code"]
        user_code = device_json["user_code"]
        verification_uri = device_json["verification_uri"]
        expires_in = device_json["expires_in"]
        interval = device_json.get("interval", 5)

        print(f"🔐 Device Code Authentication")
        print(f"   1. Visit: {verification_uri}")
        print(f"   2. Enter code: {user_code}")
        print(f"   3. Waiting for approval...")

        # Poll for token
        token_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
            "client_id": self.client_id,
        }
        if self.client_secret:
            token_data["client_secret"] = self.client_secret

        start_time = time.time()
        while time.time() - start_time < expires_in:
            time.sleep(interval)

            response = httpx.post(self.token_endpoint, data=token_data, timeout=30.0)
            if response.status_code == 200:
                token_json = response.json()
                print("✅ Authentication successful!")
                return OIDCToken(
                    access_token=token_json["access_token"],
                    refresh_token=token_json.get("refresh_token"),
                    expires_at=datetime.now(timezone.utc)
                    + timedelta(seconds=token_json["expires_in"]),
                )
            elif response.status_code == 400:
                error = response.json().get("error")
                if error == "authorization_pending":
                    print("   ⏳ Waiting for user approval...")
                    continue
                elif error == "slow_down":
                    interval += 5
                    continue
                else:
                    raise RuntimeError(f"Authentication failed: {error}")

        raise RuntimeError("Device code authentication timed out")

    def refresh(self, refresh_token: str) -> OIDCToken:
        """Refresh access token using refresh token.

        Args:
            refresh_token: Refresh token from previous authentication

        Returns:
            New OIDCToken with refreshed access token

        Raises:
            httpx.HTTPStatusError: If refresh fails
        """
        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
        }
        if self.client_secret:
            token_data["client_secret"] = self.client_secret

        response = httpx.post(self.token_endpoint, data=token_data, timeout=30.0)
        response.raise_for_status()
        token_json = response.json()

        return OIDCToken(
            access_token=token_json["access_token"],
            refresh_token=token_json.get("refresh_token", refresh_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=token_json["expires_in"]),
        )

    def introspect(self, token: str) -> dict[str, Any]:
        """Introspect token (validate with Keycloak).

        Args:
            token: Access token to introspect

        Returns:
            Token introspection response

        Raises:
            httpx.HTTPStatusError: If introspection fails
        """
        introspect_endpoint = f"{self.realm_url}/protocol/openid-connect/token/introspect"
        data = {
            "token": token,
            "client_id": self.client_id,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret

        response = httpx.post(introspect_endpoint, data=data, timeout=30.0)
        response.raise_for_status()
        return response.json()
