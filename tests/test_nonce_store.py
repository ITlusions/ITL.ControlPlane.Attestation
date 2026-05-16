"""Tests for pki/nonce_store.py — issue #7."""
from __future__ import annotations


import pytest

from attestation.pki.nonce_store import NonceStore


class TestNonceStore:
    @pytest.fixture()
    def store(self):
        return NonceStore(ttl_seconds=2)

    def test_issue_returns_32_byte_nonce(self, store):
        nonce_id, nonce_bytes, expires_at = store.issue()
        assert isinstance(nonce_id, str) and len(nonce_id) == 32
        assert len(nonce_bytes) == 32

    def test_consume_returns_correct_bytes(self, store):
        nonce_id, nonce_bytes, _ = store.issue()
        consumed = store.consume(nonce_id)
        assert consumed == nonce_bytes

    def test_double_consume_raises_value_error(self, store):
        nonce_id, _, _ = store.issue()
        store.consume(nonce_id)
        with pytest.raises(ValueError, match="already been consumed"):
            store.consume(nonce_id)

    def test_unknown_nonce_raises_key_error(self, store):
        with pytest.raises(KeyError):
            store.consume("deadbeef" * 4)

    def test_expired_nonce_raises_timeout_error(self, store):
        nonce_id, _, _ = store.issue()
        # Advance past TTL using a fresh store with TTL=0
        short_store = NonceStore(ttl_seconds=0)
        nid2, _, _ = short_store.issue()
        with pytest.raises(TimeoutError, match="expired"):
            short_store.consume(nid2)

    def test_nonces_are_unique(self, store):
        ids = {store.issue()[0] for _ in range(50)}
        assert len(ids) == 50

    def test_peek_does_not_consume(self, store):
        nonce_id, nonce_bytes, _ = store.issue()
        peeked = store.peek(nonce_id)
        assert peeked == nonce_bytes
        # Can still consume after peek
        consumed = store.consume(nonce_id)
        assert consumed == nonce_bytes
