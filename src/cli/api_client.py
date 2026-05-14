"""REST API client for ITL Attestation Service."""
from __future__ import annotations

from typing import Any

import httpx


class AttestationClient:
    """HTTP client for attestation service API."""

    def __init__(self, base_url: str, access_token: str | None = None) -> None:
        """Initialize attestation API client.

        Args:
            base_url: Base URL of attestation service (e.g. http://localhost:9000)
            access_token: Optional OIDC access token for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.client = httpx.Client(timeout=30.0)

    def _headers(self) -> dict[str, str]:
        """Build request headers with auth token."""
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def set_token(self, access_token: str) -> None:
        """Update access token.

        Args:
            access_token: New OIDC access token
        """
        self.access_token = access_token

    # Machine endpoints

    def list_machines(
        self, status: str | None = None, role: str | None = None
    ) -> list[dict[str, Any]]:
        """List all machines with optional filters.

        Args:
            status: Filter by status (pending_approval, registered, attested, locked, revoked)
            role: Filter by role (controlplane, worker-infra, worker-app)

        Returns:
            List of machine dictionaries
        """
        params = {}
        if status:
            params["status"] = status
        if role:
            params["role"] = role

        response = self.client.get(
            f"{self.base_url}/api/v1/machines",
            headers=self._headers(),
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def get_machine(self, machine_id: str) -> dict[str, Any]:
        """Get machine by ID.

        Args:
            machine_id: Machine UUID

        Returns:
            Machine dictionary
        """
        response = self.client.get(
            f"{self.base_url}/api/v1/machines/{machine_id}",
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    def approve_machine(self, machine_id: str, reason: str | None = None) -> dict[str, Any]:
        """Approve a pending machine.

        Args:
            machine_id: Machine UUID
            reason: Optional approval reason

        Returns:
            Updated machine dictionary
        """
        data = {}
        if reason:
            data["reason"] = reason

        response = self.client.post(
            f"{self.base_url}/api/v1/machines/{machine_id}/approve",
            headers=self._headers(),
            json=data,
        )
        response.raise_for_status()
        return response.json()

    def lock_machine(self, machine_id: str, reason: str | None = None) -> dict[str, Any]:
        """Lock a machine (temporary disable).

        Args:
            machine_id: Machine UUID
            reason: Optional lock reason

        Returns:
            Updated machine dictionary
        """
        data = {}
        if reason:
            data["reason"] = reason

        response = self.client.post(
            f"{self.base_url}/api/v1/machines/{machine_id}/lock",
            headers=self._headers(),
            json=data,
        )
        response.raise_for_status()
        return response.json()

    def unlock_machine(self, machine_id: str, reason: str | None = None) -> dict[str, Any]:
        """Unlock a locked machine.

        Args:
            machine_id: Machine UUID
            reason: Optional unlock reason

        Returns:
            Updated machine dictionary
        """
        data = {}
        if reason:
            data["reason"] = reason

        response = self.client.post(
            f"{self.base_url}/api/v1/machines/{machine_id}/unlock",
            headers=self._headers(),
            json=data,
        )
        response.raise_for_status()
        return response.json()

    def revoke_machine(self, machine_id: str, reason: str | None = None) -> dict[str, Any]:
        """Revoke a machine (permanent disable).

        Args:
            machine_id: Machine UUID
            reason: Optional revocation reason

        Returns:
            Updated machine dictionary
        """
        data = {}
        if reason:
            data["reason"] = reason

        response = self.client.post(
            f"{self.base_url}/api/v1/machines/{machine_id}/revoke",
            headers=self._headers(),
            json=data,
        )
        response.raise_for_status()
        return response.json()

    def delete_machine(self, machine_id: str) -> None:
        """Delete a machine (admin only).

        Args:
            machine_id: Machine UUID
        """
        response = self.client.delete(
            f"{self.base_url}/api/v1/machines/{machine_id}",
            headers=self._headers(),
        )
        response.raise_for_status()

    # Audit log endpoints

    def list_audit_logs(
        self,
        machine_id: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> dict[str, Any]:
        """List audit log entries.

        Args:
            machine_id: Optional filter by machine ID
            page: Page number (1-indexed)
            per_page: Items per page

        Returns:
            Paginated audit log response
        """
        params = {"page": page, "per_page": per_page}
        if machine_id:
            params["machine_id"] = machine_id

        response = self.client.get(
            f"{self.base_url}/api/v1/audit",
            headers=self._headers(),
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def verify_audit_chain(self) -> dict[str, Any]:
        """Verify cryptographic integrity of audit log chain.

        Returns:
            Verification result dictionary
        """
        response = self.client.get(
            f"{self.base_url}/api/v1/audit/verify",
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    # Health and status endpoints

    def health(self) -> dict[str, Any]:
        """Get service health status.

        Returns:
            Health status dictionary
        """
        response = self.client.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()

    def __enter__(self) -> AttestationClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
