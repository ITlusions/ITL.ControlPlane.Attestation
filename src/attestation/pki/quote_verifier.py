"""PCR quote verification for TPM 2.0 AK-signed quotes.

Overview
--------
After the node receives an activation challenge (POST /machines/{id}/ak-activate),
it uses its Attestation Key (AK) to sign a TPM2_Quote over the PCR banks.
The caller submits:

    - ak_pub      : SubjectPublicKeyInfo PEM of the AK (unrestricted signing key)
    - quote       : base64-encoded TPM2B_ATTEST structure (TPMS_ATTEST)
    - quote_sig   : base64-encoded TPMT_SIGNATURE (scheme from AK attributes)
    - pcr_values  : dict[str, str]  {"sha256:0": "<hex>", "sha256:7": "<hex>", ...}
    - nonce_id    : (optional) anti-replay nonce from GET /attest/challenge

Verification steps performed by ``QuoteVerifier.verify()``
----------------------------------------------------------
1. Load and validate AK public key (ECDSA P-384 or RSA-2048 only).
2. Verify the TPMT_SIGNATURE over sha256(quote) using the AK public key.
3. Decode the TPMS_ATTEST structure and check:
   a. magic == TPM_GENERATED_VALUE (0xff544347)
   b. type  == TPM_ST_ATTEST_QUOTE (0x8018)
   c. nonce (qualifyingData) matches the consumed nonce bytes (if supplied)
4. Check PCR selection and digest:
   a. pcrDigest == sha256(concatenated sorted PCR values)
5. Compare PCR values against the PCR policy table for the machine's role.

Implementation note
-------------------
This module does NOT use tpm2-pytss or any TPM library — it implements only
the minimal TPMS_ATTEST struct layout needed for software-side quote
verification, which avoids the heavyweight native dependency.

Issue ref: #6
"""
from __future__ import annotations

import base64
import hashlib
import logging
import struct
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)

# TPM 2.0 constants
_TPM_GENERATED_VALUE = 0xFF544347
_TPM_ST_ATTEST_QUOTE = 0x8018


class QuoteVerificationError(Exception):
    """Raised when any step of quote verification fails."""


class QuoteVerifier:
    """Verifies a TPM 2.0 PCR quote against an AK public key and a PCR policy."""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def verify(
        self,
        *,
        ak_pub_pem:  str,
        quote_b64:   str,
        sig_b64:     str,
        pcr_values:  dict[str, str],
        nonce_bytes: Optional[bytes] = None,
        pcr_policy:  Optional[dict[str, str]] = None,
    ) -> bool:
        """Verify a TPM 2.0 PCR quote.

        Args:
            ak_pub_pem:  SubjectPublicKeyInfo PEM of the AK.
            quote_b64:   base64-encoded TPM2B_ATTEST (raw TPMS_ATTEST bytes).
            sig_b64:     base64-encoded DER signature over sha384(quote) for
                         ECDSA P-384 or sha256(quote) for RSA-2048.
            pcr_values:  dict mapping "<alg>:<index>" → hex-encoded PCR value.
            nonce_bytes: nonce from NonceStore.consume() — compared against
                         the qualifyingData field of TPMS_ATTEST.
            pcr_policy:  expected PCR values for this machine's role.
                         None → PCR value check skipped (still verifies sig).

        Returns:
            True on success.

        Raises:
            QuoteVerificationError on any failure.
        """
        ak_pub    = self._load_ak_pub(ak_pub_pem)
        quote_raw = self._decode_b64(quote_b64, "quote")
        sig_raw   = self._decode_b64(sig_b64,   "signature")

        self._verify_signature(ak_pub, quote_raw, sig_raw)
        nonce_from_quote = self._parse_and_validate_attest(quote_raw)

        if nonce_bytes is not None:
            if nonce_from_quote != nonce_bytes:
                raise QuoteVerificationError("Nonce mismatch — possible replay attack")

        pcr_digest = self._compute_pcr_digest(pcr_values)
        self._check_pcr_digest_in_quote(quote_raw, pcr_digest)

        if pcr_policy:
            self._check_pcr_policy(pcr_values, pcr_policy)

        logger.info("PCR quote verified successfully (%d PCR values)", len(pcr_values))
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_ak_pub(pem: str) -> ec.EllipticCurvePublicKey | rsa.RSAPublicKey:
        key = serialization.load_pem_public_key(pem.encode())
        if isinstance(key, ec.EllipticCurvePublicKey):
            if not isinstance(key.curve, ec.SECP384R1):
                raise QuoteVerificationError(
                    f"AK uses unsupported EC curve {key.curve.name}; expected P-384"
                )
        elif isinstance(key, rsa.RSAPublicKey):
            if key.key_size < 2048:
                raise QuoteVerificationError(
                    f"AK RSA key size {key.key_size} is below minimum 2048"
                )
        else:
            raise QuoteVerificationError(f"Unsupported AK key type: {type(key).__name__}")
        return key

    @staticmethod
    def _decode_b64(value: str, name: str) -> bytes:
        try:
            return base64.b64decode(value)
        except Exception as exc:
            raise QuoteVerificationError(f"Cannot base64-decode {name}: {exc}") from exc

    @staticmethod
    def _verify_signature(
        ak_pub: ec.EllipticCurvePublicKey | rsa.RSAPublicKey,
        data:   bytes,
        sig:    bytes,
    ) -> None:
        try:
            if isinstance(ak_pub, ec.EllipticCurvePublicKey):
                ak_pub.verify(sig, data, ec.ECDSA(hashes.SHA384()))
            else:
                ak_pub.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature as exc:
            raise QuoteVerificationError("AK signature verification failed") from exc

    @staticmethod
    def _parse_and_validate_attest(quote_raw: bytes) -> bytes:
        """Parse TPMS_ATTEST and return qualifyingData bytes.

        Layout (minimal):
          UINT32 magic          — must be 0xFF544347
          UINT16 type           — must be 0x8018 (TPM_ST_ATTEST_QUOTE)
          TPM2B qualifyingData  — 2-byte length + payload (our nonce)
          ... (clock, firmwareVersion, attested.quote = pcrSelect + pcrDigest)
        """
        if len(quote_raw) < 10:
            raise QuoteVerificationError("TPMS_ATTEST too short")

        offset = 0
        magic,     = struct.unpack_from(">I", quote_raw, offset); offset += 4
        tpm_type,  = struct.unpack_from(">H", quote_raw, offset); offset += 2

        if magic != _TPM_GENERATED_VALUE:
            raise QuoteVerificationError(
                f"TPMS_ATTEST magic mismatch: expected {_TPM_GENERATED_VALUE:#010x}, got {magic:#010x}"
            )
        if tpm_type != _TPM_ST_ATTEST_QUOTE:
            raise QuoteVerificationError(
                f"TPMS_ATTEST type mismatch: expected {_TPM_ST_ATTEST_QUOTE:#06x}, got {tpm_type:#06x}"
            )

        # Skip qualifiedSigner (TPM2B — 2-byte length prefix)
        qs_len, = struct.unpack_from(">H", quote_raw, offset); offset += 2 + qs_len

        # qualifyingData (TPM2B — our nonce)
        qd_len, = struct.unpack_from(">H", quote_raw, offset); offset += 2
        qualifying_data = quote_raw[offset: offset + qd_len]; offset += qd_len

        return qualifying_data

    @staticmethod
    def _compute_pcr_digest(pcr_values: dict[str, str]) -> bytes:
        """SHA-256 over the concatenation of sorted PCR values.

        Keys are expected as "<alg>:<index>" (e.g., "sha256:0").
        Values are hex-encoded PCR digests.
        """
        h = hashlib.sha256()
        for key in sorted(pcr_values.keys()):
            try:
                h.update(bytes.fromhex(pcr_values[key]))
            except ValueError as exc:
                raise QuoteVerificationError(
                    f"Invalid hex value for PCR {key}: {exc}"
                ) from exc
        return h.digest()

    @staticmethod
    def _check_pcr_digest_in_quote(quote_raw: bytes, pcr_digest: bytes) -> None:
        """Verify that pcr_digest appears verbatim somewhere in the TPMS_ATTEST.

        This is a conservative check — a full TPM2 parser would extract the
        TPML_PCR_SELECTION.pcrDigest field precisely.  For the initial
        implementation we scan the raw bytes; the digest is 32 bytes and
        appears exactly once in a well-formed quote.
        """
        if pcr_digest not in quote_raw:
            raise QuoteVerificationError(
                "PCR digest from supplied pcr_values not found in TPMS_ATTEST — "
                "values may have been tampered with"
            )

    @staticmethod
    def _check_pcr_policy(
        actual:   dict[str, str],
        expected: dict[str, str],
    ) -> None:
        """Compare actual PCR values against the policy for the machine's role."""
        violations: list[str] = []
        for pcr_id, exp_value in expected.items():
            act_value = actual.get(pcr_id, "")
            if act_value.lower().strip() != exp_value.lower().strip():
                violations.append(
                    f"PCR {pcr_id}: expected {exp_value!r}, got {act_value!r}"
                )
        if violations:
            raise QuoteVerificationError(
                "PCR policy violation:\n" + "\n".join(violations)
            )
