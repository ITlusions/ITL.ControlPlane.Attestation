"""HTTP client for the ITL Attestation REST API.

Uses SDK schemas for responses (MachineDetail, RegisterResponse) and the
attestation service's request schemas to stay in sync with the API contract.
"""

from __future__ import annotations

from typing import Optional

import requests

from attestation.schemas.requests import (
    ApproveRequest,
    LockRequest,
    RegisterRequest,
    RevokeRequest,
)
from sdk import MachineDetail, RegisterResponse


class AttestationApiError(Exception):
    """Raised when the Attestation API returns a non-2xx status."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        super().__init__(f"Attestation API error {status}: {body}")


class AttestationClient:
    """Synchronous HTTP client for the Attestation Service."""

    def __init__(self, endpoint: str, token: str, timeout: int = 30) -> None:
        self._base = endpoint.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    def _url(self, path: str) -> str:
        return f"{self._base}/api/v1{path}"

    def _check(self, response: requests.Response) -> dict:
        if not response.ok:
            raise AttestationApiError(response.status_code, response.text)
        return response.json()

    # ------------------------------------------------------------------ #
    # Registration                                                          #
    # ------------------------------------------------------------------ #

    def register(self, req: RegisterRequest) -> RegisterResponse:
        """POST /api/v1/register"""
        return RegisterResponse.model_validate(
            self._check(
                self._session.post(
                    self._url("/register"),
                    content=req.model_dump_json(exclude_none=True),
                    timeout=self._timeout,
                )
            )
        )

    # ------------------------------------------------------------------ #
    # Machine admin                                                         #
    # ------------------------------------------------------------------ #

    def get_machine(self, machine_id: str) -> MachineDetail:
        """GET /api/v1/machines/{machine_id}"""
        return MachineDetail.model_validate(
            self._check(self._session.get(self._url(f"/machines/{machine_id}"), timeout=self._timeout))
        )

    def list_machines(self) -> list[MachineDetail]:
        """GET /api/v1/machines"""
        return [
            MachineDetail.model_validate(item)
            for item in self._check(self._session.get(self._url("/machines"), timeout=self._timeout))
        ]

    def approve_machine(self, machine_id: str, req: ApproveRequest) -> MachineDetail:
        """POST /api/v1/machines/{machine_id}/approve"""
        return MachineDetail.model_validate(
            self._check(
                self._session.post(
                    self._url(f"/machines/{machine_id}/approve"),
                    content=req.model_dump_json(exclude_none=True),
                    timeout=self._timeout,
                )
            )
        )

    def revoke_machine(self, machine_id: str, req: Optional[RevokeRequest] = None) -> MachineDetail:
        """POST /api/v1/machines/{machine_id}/revoke"""
        body = (req or RevokeRequest()).model_dump_json(exclude_none=True)
        return MachineDetail.model_validate(
            self._check(
                self._session.post(
                    self._url(f"/machines/{machine_id}/revoke"),
                    content=body,
                    timeout=self._timeout,
                )
            )
        )

    def lock_machine(self, machine_id: str, req: Optional[LockRequest] = None) -> MachineDetail:
        """POST /api/v1/machines/{machine_id}/lock"""
        body = (req or LockRequest()).model_dump_json(exclude_none=True)
        return MachineDetail.model_validate(
            self._check(
                self._session.post(
                    self._url(f"/machines/{machine_id}/lock"),
                    content=body,
                    timeout=self._timeout,
                )
            )
        )

    def unlock_machine(self, machine_id: str) -> MachineDetail:
        """POST /api/v1/machines/{machine_id}/unlock"""
        return MachineDetail.model_validate(
            self._check(
                self._session.post(self._url(f"/machines/{machine_id}/unlock"), content="{}", timeout=self._timeout)
            )
        )

