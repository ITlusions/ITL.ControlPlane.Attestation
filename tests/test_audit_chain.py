"""Tests for the cryptographically chained audit log.

Verifies:
  - append() stores correct prev_hash / entry_hash values
  - verify_chain() returns valid=True on an intact chain
  - verify_chain() returns valid=False when an entry's content is modified
  - verify_chain() returns valid=False when a prev_hash is tampered
  - verify_chain() handles an empty table (valid=True, entries=0)
  - compute_entry_hash() is deterministic

Issue ref: security — cryptographically chained append-only audit log
"""
from __future__ import annotations


import pytest
from sqlmodel import Session, SQLModel, create_engine

from attestation.models.operator import AuditLogRow
from attestation.repositories.operator_repo import (
    GENESIS_HASH,
    AuditRepository,
    compute_entry_hash,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    """In-memory SQLite session — fresh for every test."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def repo(db_session: Session) -> AuditRepository:
    return AuditRepository(db_session)


def _entry(action: str = "approve", machine_id: str = "m-1") -> AuditLogRow:
    return AuditLogRow(
        operator_cn = "alice",
        action      = action,
        machine_id  = machine_id,
        prev_state  = "pending_approval",
        new_state   = "registered",
        detail      = "test entry",
    )


# ---------------------------------------------------------------------------
# compute_entry_hash — determinism
# ---------------------------------------------------------------------------

class TestComputeEntryHash:

    def test_deterministic(self):
        """Same entry data always produces the same hash."""
        entry = _entry()
        entry.prev_hash = GENESIS_HASH
        h1 = compute_entry_hash(entry)
        h2 = compute_entry_hash(entry)
        assert h1 == h2

    def test_returns_64_hex_chars(self):
        """SHA-256 hex digest is exactly 64 characters."""
        entry = _entry()
        entry.prev_hash = GENESIS_HASH
        assert len(compute_entry_hash(entry)) == 64
        assert all(c in "0123456789abcdef" for c in compute_entry_hash(entry))

    def test_different_actions_differ(self):
        e1 = _entry(action="approve")
        e2 = _entry(action="revoke")
        e1.prev_hash = e2.prev_hash = GENESIS_HASH
        assert compute_entry_hash(e1) != compute_entry_hash(e2)

    def test_different_prev_hash_differs(self):
        e1 = _entry()
        e2 = _entry()
        e1.prev_hash = GENESIS_HASH
        e2.prev_hash = "a" * 64
        assert compute_entry_hash(e1) != compute_entry_hash(e2)


# ---------------------------------------------------------------------------
# AuditRepository.append — hash assignment
# ---------------------------------------------------------------------------

class TestAuditRepositoryAppend:

    def test_first_entry_prev_hash_is_genesis(self, repo: AuditRepository):
        saved = repo.append(_entry())
        assert saved.prev_hash == GENESIS_HASH

    def test_first_entry_hash_non_empty(self, repo: AuditRepository):
        saved = repo.append(_entry())
        assert len(saved.entry_hash) == 64

    def test_second_entry_prev_hash_equals_first_entry_hash(self, repo: AuditRepository):
        first  = repo.append(_entry(action="approve"))
        second = repo.append(_entry(action="revoke"))
        assert second.prev_hash == first.entry_hash

    def test_chain_of_three_entries(self, repo: AuditRepository):
        e1 = repo.append(_entry(action="approve"))
        e2 = repo.append(_entry(action="lock"))
        e3 = repo.append(_entry(action="unlock"))
        assert e1.prev_hash == GENESIS_HASH
        assert e2.prev_hash == e1.entry_hash
        assert e3.prev_hash == e2.entry_hash


# ---------------------------------------------------------------------------
# AuditRepository.verify_chain — intact chain
# ---------------------------------------------------------------------------

class TestVerifyChainValid:

    def test_empty_chain_is_valid(self, repo: AuditRepository):
        result = repo.verify_chain()
        assert result["valid"]       is True
        assert result["entries"]     == 0
        assert result["root_hash"]   is None

    def test_single_entry_chain_valid(self, repo: AuditRepository):
        repo.append(_entry())
        result = repo.verify_chain()
        assert result["valid"]   is True
        assert result["entries"] == 1
        assert len(result["root_hash"]) == 64

    def test_multi_entry_chain_valid(self, repo: AuditRepository):
        for action in ("approve", "lock", "unlock", "revoke"):
            repo.append(_entry(action=action))
        result = repo.verify_chain()
        assert result["valid"]   is True
        assert result["entries"] == 4
        assert result["first_invalid_id"] is None
        assert result["error"]            is None


# ---------------------------------------------------------------------------
# AuditRepository.verify_chain — tamper detection
# ---------------------------------------------------------------------------

class TestVerifyChainTampered:

    def test_tampered_entry_hash_detected(self, repo: AuditRepository, db_session: Session):
        """Directly overwrite an entry_hash in the DB → verify returns valid=False."""
        row = repo.append(_entry())
        # Directly corrupt the stored hash (simulates an insider modifying the DB)
        row.entry_hash = "deadbeef" * 8  # 64 hex chars but wrong
        db_session.add(row)
        db_session.commit()

        result = repo.verify_chain()
        assert result["valid"]            is False
        assert result["first_invalid_id"] == row.id
        assert "entry_hash mismatch"      in result["error"]

    def test_tampered_content_detected(self, repo: AuditRepository, db_session: Session):
        """Modifying a content field without updating entry_hash → verify returns valid=False."""
        row = repo.append(_entry(action="approve"))
        # Mutate a content field to simulate log tampering
        row.action = "revoke"
        db_session.add(row)
        db_session.commit()

        result = repo.verify_chain()
        assert result["valid"]            is False
        assert result["first_invalid_id"] == row.id

    def test_tampered_prev_hash_in_second_entry(self, repo: AuditRepository, db_session: Session):
        """A broken chain link (wrong prev_hash on entry 2) is detected."""
        repo.append(_entry(action="approve"))
        second = repo.append(_entry(action="lock"))
        # Break the link by pointing prev_hash to garbage (a string that is neither
        # GENESIS_HASH nor the first entry's real entry_hash)
        second.prev_hash  = "ab" * 32   # 64 hex chars — does not match entry 1's hash
        # Recompute entry_hash so it's internally consistent (simulates sophisticated tamper)
        second.entry_hash = compute_entry_hash(second)
        db_session.add(second)
        db_session.commit()

        result = repo.verify_chain()
        assert result["valid"]            is False
        assert result["first_invalid_id"] == second.id
        assert "prev_hash mismatch"       in result["error"]

    def test_tampered_first_entry_cascades(self, repo: AuditRepository, db_session: Session):
        """Modifying the first entry invalidates the whole chain from that point."""
        first  = repo.append(_entry(action="approve"))
        _second = repo.append(_entry(action="lock"))
        # Tamper first entry content without fixing entry_hash
        first.detail = "tampered"
        db_session.add(first)
        db_session.commit()

        result = repo.verify_chain()
        assert result["valid"] is False
        # The first broken link is on the first entry
        assert result["first_invalid_id"] == first.id
