"""Tests for dual-control approval, audit logging, and OIDC/break-glass auth.

Issue ref: security — per-operator identity and dual-control approval
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from attestation.handlers.machines import MachineAdminHandler
from attestation.models.machine import MachineRow, MachineStatus, NodeRole
from attestation.models.operator import ApprovalRequestRow, AuditLogRow
from attestation.repositories.operator_repo import AuditRepository, ApprovalRepository
from attestation.schemas.requests import ApproveRequest
from attestation.schemas.responses import MachineDetail, PendingApprovalResponse


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _make_machine(
    machine_id: str | None = None,
    role: NodeRole = NodeRole.controlplane,
    status: MachineStatus = MachineStatus.pending_approval,
) -> MachineRow:
    return MachineRow(
        machine_id     = machine_id or str(uuid.uuid4()),
        ek_fingerprint = "a" * 96,
        ek_source      = "cert",
        role           = role,
        status         = status,
    )


def _mock_machine_repo(machine: MachineRow | None) -> MagicMock:
    repo = MagicMock()
    repo.get_by_id.return_value = machine
    repo.save.side_effect = lambda m: m
    return repo


def _mock_audit_repo() -> MagicMock:
    repo = MagicMock(spec=AuditRepository)
    repo.append.side_effect = lambda e: e
    return repo


def _mock_approval_repo(
    pending: list[ApprovalRequestRow] | None = None,
    all_rows: list[ApprovalRequestRow] | None = None,
) -> MagicMock:
    repo = MagicMock(spec=ApprovalRepository)
    repo.get_pending_for_machine.return_value = pending or []
    repo.list_for_machine.return_value = all_rows or []
    repo.create.side_effect = lambda r: r
    repo.mark_consumed.return_value = None
    return repo


def _pending_row(
    machine_id: str,
    operator_cn: str,
    role: str = "controlplane",
    seconds_until_expiry: int = 600,
) -> ApprovalRequestRow:
    now = datetime.now(timezone.utc)
    return ApprovalRequestRow(
        id          = 1,
        machine_id  = machine_id,
        operator_cn = operator_cn,
        role        = role,
        expires_at  = now + timedelta(seconds=seconds_until_expiry),
    )


def _handler(
    machine: MachineRow | None,
    pending: list[ApprovalRequestRow] | None = None,
    all_rows: list[ApprovalRequestRow] | None = None,
) -> MachineAdminHandler:
    return MachineAdminHandler(
        machine_repo  = _mock_machine_repo(machine),
        audit_repo    = _mock_audit_repo(),
        approval_repo = _mock_approval_repo(pending, all_rows),
    )


def _approve_req(role: NodeRole = NodeRole.controlplane) -> ApproveRequest:
    return ApproveRequest(role=role, hostname="cp-01")


# ---------------------------------------------------------------------------
# Dual-control: first approval returns 202
# ---------------------------------------------------------------------------

class TestDualControlFirstApproval:

    @pytest.fixture(autouse=True)
    def patch_settings(self):
        """Enable dual-control for controlplane role."""
        with patch("attestation.handlers.machines.get_settings") as mock_settings:
            s = MagicMock()
            s.dual_control_roles            = ["controlplane"]
            s.dual_control_quorum           = 2
            s.dual_control_window_seconds   = 600
            s.service_base_url              = "https://attest.itlusions.com"
            mock_settings.return_value = s
            yield

    def test_first_approval_returns_202(self):
        machine = _make_machine(role=NodeRole.controlplane)
        body, code = _handler(machine).approve(machine.machine_id, _approve_req(), "alice")
        assert code == 202
        assert isinstance(body, PendingApprovalResponse)
        assert body.status == "pending_second_approval"
        assert body.approvals_received == 1
        assert body.approvals_required == 2

    def test_first_approval_creates_pending_row(self):
        machine = _make_machine(role=NodeRole.controlplane)
        approval_repo = _mock_approval_repo()
        handler = MachineAdminHandler(
            machine_repo  = _mock_machine_repo(machine),
            audit_repo    = _mock_audit_repo(),
            approval_repo = approval_repo,
        )
        handler.approve(machine.machine_id, _approve_req(), "alice")
        approval_repo.create.assert_called_once()
        created: ApprovalRequestRow = approval_repo.create.call_args[0][0]
        assert created.operator_cn == "alice"
        assert created.machine_id  == machine.machine_id

    def test_same_operator_second_call_still_202(self):
        """If alice votes again she cannot be her own quorum partner."""
        machine = _make_machine(role=NodeRole.controlplane)
        # Simulate alice's existing pending vote
        existing = _pending_row(machine.machine_id, "alice")
        approval_repo = _mock_approval_repo(pending=[existing])
        handler = MachineAdminHandler(
            machine_repo  = _mock_machine_repo(machine),
            audit_repo    = _mock_audit_repo(),
            approval_repo = approval_repo,
        )
        body, code = handler.approve(machine.machine_id, _approve_req(), "alice")
        assert code == 202
        # Should NOT create another row since alice already voted
        approval_repo.create.assert_not_called()

    def test_first_approval_writes_audit_vote(self):
        machine = _make_machine(role=NodeRole.controlplane)
        audit_repo = _mock_audit_repo()
        handler = MachineAdminHandler(
            machine_repo  = _mock_machine_repo(machine),
            audit_repo    = audit_repo,
            approval_repo = _mock_approval_repo(),
        )
        handler.approve(machine.machine_id, _approve_req(), "alice")
        audit_repo.append.assert_called_once()
        entry: AuditLogRow = audit_repo.append.call_args[0][0]
        assert entry.operator_cn == "alice"
        assert entry.action      == "approve_vote"


# ---------------------------------------------------------------------------
# Dual-control: second approval completes the flow (200)
# ---------------------------------------------------------------------------

class TestDualControlSecondApproval:

    @pytest.fixture(autouse=True)
    def patch_settings(self):
        with patch("attestation.handlers.machines.get_settings") as mock_settings:
            s = MagicMock()
            s.dual_control_roles            = ["controlplane"]
            s.dual_control_quorum           = 2
            s.dual_control_window_seconds   = 600
            s.service_base_url              = "https://attest.itlusions.com"
            mock_settings.return_value = s
            yield

    def test_second_operator_approval_returns_200(self):
        machine  = _make_machine(role=NodeRole.controlplane)
        existing = _pending_row(machine.machine_id, "alice")
        body, code = _handler(machine, pending=[existing]).approve(
            machine.machine_id, _approve_req(), "bob"
        )
        assert code == 200
        assert isinstance(body, MachineDetail)
        assert body.status == MachineStatus.registered.value

    def test_second_approval_consumes_first_vote(self):
        machine  = _make_machine(role=NodeRole.controlplane)
        existing = _pending_row(machine.machine_id, "alice")
        approval_repo = _mock_approval_repo(pending=[existing])
        handler = MachineAdminHandler(
            machine_repo  = _mock_machine_repo(machine),
            audit_repo    = _mock_audit_repo(),
            approval_repo = approval_repo,
        )
        handler.approve(machine.machine_id, _approve_req(), "bob")
        approval_repo.mark_consumed.assert_called_once_with(existing.id)

    def test_second_approval_writes_two_audit_entries(self):
        """One 'approve_vote' entry for the second vote, one 'approve' for the final action."""
        machine  = _make_machine(role=NodeRole.controlplane)
        existing = _pending_row(machine.machine_id, "alice")
        audit_repo = _mock_audit_repo()
        handler = MachineAdminHandler(
            machine_repo  = _mock_machine_repo(machine),
            audit_repo    = audit_repo,
            approval_repo = _mock_approval_repo(pending=[existing]),
        )
        handler.approve(machine.machine_id, _approve_req(), "bob")
        calls = [c[0][0] for c in audit_repo.append.call_args_list]
        actions = [e.action for e in calls]
        assert "approve_vote" in actions
        assert "approve"      in actions


# ---------------------------------------------------------------------------
# Dual-control: quorum expiry
# ---------------------------------------------------------------------------

class TestDualControlExpiry:

    @pytest.fixture(autouse=True)
    def patch_settings(self):
        with patch("attestation.handlers.machines.get_settings") as mock_settings:
            s = MagicMock()
            s.dual_control_roles            = ["controlplane"]
            s.dual_control_quorum           = 2
            s.dual_control_window_seconds   = 600
            s.service_base_url              = "https://attest.itlusions.com"
            mock_settings.return_value = s
            yield

    def test_expired_vote_not_counted_as_pending(self):
        """get_pending_for_machine already filters expired rows; an expired vote
        means the second operator arrives to an empty queue and gets 202."""
        machine = _make_machine(role=NodeRole.controlplane)
        # The repo returns no pending rows (expired ones filtered out by the repo)
        body, code = _handler(machine, pending=[]).approve(
            machine.machine_id, _approve_req(), "bob"
        )
        assert code == 202

    def test_non_dual_control_role_approves_immediately(self):
        """worker-app is not in dual_control_roles → immediate 200."""
        machine = _make_machine(role=NodeRole.worker_app)
        body, code = _handler(machine, pending=[]).approve(
            machine.machine_id,
            ApproveRequest(role=NodeRole.worker_app, hostname="w-01"),
            "alice",
        )
        assert code == 200
        assert isinstance(body, MachineDetail)


# ---------------------------------------------------------------------------
# Break-glass (SYSTEM operator)
# ---------------------------------------------------------------------------

class TestBreakGlass:

    @pytest.fixture(autouse=True)
    def patch_settings_no_dual(self):
        with patch("attestation.handlers.machines.get_settings") as mock_settings:
            s = MagicMock()
            s.dual_control_roles           = []   # no dual-control
            s.dual_control_quorum          = 2
            s.dual_control_window_seconds  = 600
            s.service_base_url             = "https://attest.itlusions.com"
            mock_settings.return_value = s
            yield

    def test_system_operator_approves_and_audit_logged(self):
        machine    = _make_machine(role=NodeRole.worker_app)
        audit_repo = _mock_audit_repo()
        handler = MachineAdminHandler(
            machine_repo  = _mock_machine_repo(machine),
            audit_repo    = audit_repo,
            approval_repo = _mock_approval_repo(),
        )
        body, code = handler.approve(
            machine.machine_id,
            ApproveRequest(role=NodeRole.worker_app),
            "SYSTEM",
        )
        assert code == 200
        entry: AuditLogRow = audit_repo.append.call_args[0][0]
        assert entry.operator_cn == "SYSTEM"

    def test_system_revoke_logged(self):
        from attestation.schemas.requests import RevokeRequest
        machine    = _make_machine(status=MachineStatus.attested)
        audit_repo = _mock_audit_repo()
        handler = MachineAdminHandler(
            machine_repo  = _mock_machine_repo(machine),
            audit_repo    = audit_repo,
            approval_repo = _mock_approval_repo(),
        )
        handler.revoke(machine.machine_id, RevokeRequest(wipe=False), "SYSTEM")
        entry: AuditLogRow = audit_repo.append.call_args[0][0]
        assert entry.operator_cn == "SYSTEM"
        assert entry.action      == "revoke"
        assert entry.new_state   == MachineStatus.revoked.value


# ---------------------------------------------------------------------------
# Audit log — append-only
# ---------------------------------------------------------------------------

class TestAuditLog:

    def test_audit_entry_has_operator_and_state_transition(self):
        """approve() must write an AuditLogRow with prev/new state."""
        with patch("attestation.handlers.machines.get_settings") as mock_settings:
            s = MagicMock()
            s.dual_control_roles           = []
            s.dual_control_quorum          = 2
            s.dual_control_window_seconds  = 600
            s.service_base_url             = "https://attest.itlusions.com"
            mock_settings.return_value = s

            machine    = _make_machine(role=NodeRole.worker_app)
            audit_repo = _mock_audit_repo()
            handler = MachineAdminHandler(
                machine_repo  = _mock_machine_repo(machine),
                audit_repo    = audit_repo,
                approval_repo = _mock_approval_repo(),
            )
            handler.approve(
                machine.machine_id,
                ApproveRequest(role=NodeRole.worker_app),
                "niels.weistra",
            )

        entry: AuditLogRow = audit_repo.append.call_args[0][0]
        assert entry.operator_cn == "niels.weistra"
        assert entry.prev_state  == MachineStatus.pending_approval.value
        assert entry.new_state   == MachineStatus.registered.value
        assert entry.machine_id  == machine.machine_id


# ---------------------------------------------------------------------------
# OIDC: _extract_roles helper
# ---------------------------------------------------------------------------

class TestOidcExtractRoles:

    def test_realm_roles_extracted(self):
        from attestation.pki.oidc import _extract_roles
        payload = {"realm_access": {"roles": ["attestation-operator", "default-roles-itl"]}}
        assert "attestation-operator" in _extract_roles(payload)

    def test_resource_access_roles_extracted(self):
        from attestation.pki.oidc import _extract_roles
        payload = {
            "resource_access": {
                "attestation-service": {"roles": ["attestation-operator"]}
            }
        }
        assert "attestation-operator" in _extract_roles(payload)

    def test_missing_role_returns_empty(self):
        from attestation.pki.oidc import _extract_roles
        assert _extract_roles({}) == set()

    def test_both_sources_merged(self):
        from attestation.pki.oidc import _extract_roles
        payload = {
            "realm_access": {"roles": ["role-a"]},
            "resource_access": {"client": {"roles": ["role-b"]}},
        }
        roles = _extract_roles(payload)
        assert "role-a" in roles
        assert "role-b" in roles


# ---------------------------------------------------------------------------
# OIDC: validate_operator_token (unit-level, mocked JWT decode)
# ---------------------------------------------------------------------------

class TestValidateOperatorToken:

    def _mock_jwks_client(self, signing_key_mock: Any):
        client = MagicMock()
        client.get_signing_key_from_jwt.return_value = signing_key_mock
        return client

    def test_valid_token_with_role_returns_username(self):
        from attestation.pki import oidc as oidc_mod

        signing_key = MagicMock()
        signing_key.key = "fake-key"

        payload = {
            "preferred_username": "niels.weistra",
            "sub": "some-uuid",
            "realm_access": {"roles": ["attestation-operator"]},
        }

        with (
            patch.object(oidc_mod, "_get_oidc_settings",
                         return_value=("https://sts.itlusions.com/realms/itl",
                                       "attestation-service",
                                       "attestation-operator",
                                       True)),
            patch.object(oidc_mod, "_ensure_jwks_client",
                         return_value=self._mock_jwks_client(signing_key)),
            patch("jwt.decode", return_value=payload),
        ):
            result = oidc_mod.validate_operator_token("fake.jwt.token")
        assert result == "niels.weistra"

    def test_missing_role_raises_value_error(self):
        from attestation.pki import oidc as oidc_mod

        signing_key = MagicMock()
        signing_key.key = "fake-key"

        payload = {
            "preferred_username": "niels.weistra",
            "realm_access": {"roles": ["some-other-role"]},
        }

        with (
            patch.object(oidc_mod, "_get_oidc_settings",
                         return_value=("https://sts.itlusions.com/realms/itl",
                                       "attestation-service",
                                       "attestation-operator",
                                       True)),
            patch.object(oidc_mod, "_ensure_jwks_client",
                         return_value=self._mock_jwks_client(signing_key)),
            patch("jwt.decode", return_value=payload),
        ):
            with pytest.raises(ValueError, match="required role"):
                oidc_mod.validate_operator_token("fake.jwt.token")

    def test_oidc_disabled_raises_value_error(self):
        from attestation.pki import oidc as oidc_mod
        with patch.object(oidc_mod, "_get_oidc_settings",
                          return_value=("", "attestation-service", "attestation-operator", True)):
            with pytest.raises(ValueError, match="not configured"):
                oidc_mod.validate_operator_token("any.token")

    def test_expired_token_raises_value_error(self):
        import jwt as jwt_lib
        from attestation.pki import oidc as oidc_mod

        signing_key = MagicMock()
        signing_key.key = "fake-key"

        with (
            patch.object(oidc_mod, "_get_oidc_settings",
                         return_value=("https://sts.itlusions.com/realms/itl",
                                       "attestation-service",
                                       "attestation-operator",
                                       True)),
            patch.object(oidc_mod, "_ensure_jwks_client",
                         return_value=self._mock_jwks_client(signing_key)),
            patch("jwt.decode", side_effect=jwt_lib.ExpiredSignatureError("expired")),
        ):
            with pytest.raises(ValueError, match="expired"):
                oidc_mod.validate_operator_token("expired.jwt.token")

    def test_sub_used_as_fallback_identity(self):
        from attestation.pki import oidc as oidc_mod

        signing_key = MagicMock()
        signing_key.key = "fake-key"

        payload = {
            "sub": "user-uuid-1234",
            "realm_access": {"roles": ["attestation-operator"]},
            # no preferred_username
        }

        with (
            patch.object(oidc_mod, "_get_oidc_settings",
                         return_value=("https://sts.itlusions.com/realms/itl",
                                       "attestation-service",
                                       "attestation-operator",
                                       True)),
            patch.object(oidc_mod, "_ensure_jwks_client",
                         return_value=self._mock_jwks_client(signing_key)),
            patch("jwt.decode", return_value=payload),
        ):
            result = oidc_mod.validate_operator_token("fake.jwt.token")
        assert result == "user-uuid-1234"
