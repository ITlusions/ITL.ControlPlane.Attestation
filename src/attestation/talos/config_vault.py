"""Encrypted at-rest storage for Talos cluster config files.

After ``talosctl gen config`` writes plaintext YAML files to disk, this module
encrypts each file with AES-256-GCM and replaces it with a ``.enc`` blob.
The plaintext is wiped immediately after encryption.

Key material
------------
Resolved in priority order:

1. ``ITL_CONFIG_ENCRYPTION_KEY``   — 64-char hex string (32 raw bytes).
   Generate with: ``python -c "import os,secrets; print(secrets.token_hex(32))"``

2. ``ITL_CONFIG_ENCRYPTION_PASSPHRASE`` — any string, SHA-256 stretched to 32 bytes.
   Easier for dev, less secure than a dedicated key.

3. *Ephemeral random key (dev fallback)* — generated fresh on every process start.
   Encrypted configs are unreadable after a restart. A warning is emitted on
   every startup when this path is taken so it is hard to overlook in production.

Wire format
-----------
Each ``.enc`` file is a raw binary blob::

    [ nonce (12 bytes) ][ ciphertext + GCM tag (len(plaintext) + 16 bytes) ]

No header, no framing — intentionally minimal.

Usage
-----
``config_vault`` is a module-level singleton::

    from .config_vault import config_vault

    # Seal plaintext → writes <path>.enc, deletes <path>
    config_vault.seal(plaintext_path)

    # Unseal → returns plaintext str
    content = config_vault.unseal(encrypted_path)

    # Check existence
    config_vault.exists(plaintext_path)  # True if <path>.enc exists
"""

from __future__ import annotations

import hashlib
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_ENC_SUFFIX = ".enc"


class _ClusterConfigVault:
    """AES-256-GCM vault for cluster config files.

    Instantiated once at module level as ``config_vault``.
    Key is derived lazily on first use.
    """

    def __init__(self) -> None:
        self._key: bytes | None = None

    # ------------------------------------------------------------------
    # Key management
    # ------------------------------------------------------------------

    def _load_key(self) -> bytes:
        if self._key is not None:
            return self._key

        raw_hex = os.environ.get("ITL_CONFIG_ENCRYPTION_KEY", "")
        if raw_hex:
            key = bytes.fromhex(raw_hex)
            if len(key) != 32:
                raise ValueError(
                    "ITL_CONFIG_ENCRYPTION_KEY must be exactly 32 bytes (64 hex chars)"
                )
            logger.info("ClusterConfigVault: using ITL_CONFIG_ENCRYPTION_KEY")
            self._key = key
            return self._key

        passphrase = os.environ.get("ITL_CONFIG_ENCRYPTION_PASSPHRASE", "")
        if passphrase:
            self._key = hashlib.sha256(passphrase.encode()).digest()
            logger.info("ClusterConfigVault: key derived from ITL_CONFIG_ENCRYPTION_PASSPHRASE")
            return self._key

        # Ephemeral key — warn loudly
        self._key = os.urandom(32)
        logger.warning(
            "ClusterConfigVault: no encryption key configured — using ephemeral random key. "
            "Cluster configs will be UNREADABLE after a process restart. "
            "Set ITL_CONFIG_ENCRYPTION_KEY or ITL_CONFIG_ENCRYPTION_PASSPHRASE."
        )
        return self._key

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def seal(self, plaintext_path: str) -> str:
        """Encrypt *plaintext_path* → write ``<path>.enc``, delete the original.

        Args:
            plaintext_path: Absolute path to the plaintext file to encrypt.

        Returns:
            Path of the written ``.enc`` file.

        Raises:
            FileNotFoundError: *plaintext_path* does not exist.
        """
        if not os.path.exists(plaintext_path):
            raise FileNotFoundError(f"Cannot seal: file not found: {plaintext_path}")

        with open(plaintext_path, "rb") as f:
            plaintext = f.read()

        key = self._load_key()
        nonce = os.urandom(12)
        ciphertext_and_tag = AESGCM(key).encrypt(nonce, plaintext, None)

        enc_path = plaintext_path + _ENC_SUFFIX
        with open(enc_path, "wb") as f:
            f.write(nonce + ciphertext_and_tag)

        # Overwrite plaintext with zeros before unlinking (best-effort)
        try:
            with open(plaintext_path, "wb") as f:
                f.write(b"\x00" * len(plaintext))
        except OSError:
            pass
        os.unlink(plaintext_path)

        logger.debug("Sealed %s → %s", os.path.basename(plaintext_path), os.path.basename(enc_path))
        return enc_path

    def unseal(self, enc_path: str) -> str:
        """Decrypt *enc_path* and return the plaintext as a string.

        Args:
            enc_path: Absolute path to a ``.enc`` file.

        Returns:
            Decrypted plaintext as UTF-8 string.

        Raises:
            FileNotFoundError: *enc_path* does not exist.
            ValueError:        Decryption failed (wrong key / tampered blob).
        """
        if not os.path.exists(enc_path):
            raise FileNotFoundError(f"Cannot unseal: file not found: {enc_path}")

        with open(enc_path, "rb") as f:
            blob = f.read()

        if len(blob) < 12:
            raise ValueError(f"Encrypted blob too short: {enc_path}")

        nonce = blob[:12]
        ciphertext_and_tag = blob[12:]

        key = self._load_key()
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext_and_tag, None)
        except Exception as exc:
            raise ValueError(
                f"Decryption failed for {enc_path} — wrong key or corrupted data: {exc}"
            ) from exc

        return plaintext.decode("utf-8")

    def exists(self, plaintext_path: str) -> bool:
        """Return True if the encrypted counterpart of *plaintext_path* exists."""
        return os.path.exists(plaintext_path + _ENC_SUFFIX)

    def enc_path(self, plaintext_path: str) -> str:
        """Return the ``.enc`` path for a given plaintext path."""
        return plaintext_path + _ENC_SUFFIX


# Module-level singleton
config_vault = _ClusterConfigVault()
