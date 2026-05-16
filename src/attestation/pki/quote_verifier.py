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
        nonce_from_quote, pcr_digest_from_quote = self._parse_and_validate_attest(quote_raw)

        if nonce_bytes is not None:
            if nonce_from_quote != nonce_bytes:
                raise QuoteVerificationError("Nonce mismatch — possible replay attack")

        if pcr_values:
            pcr_digest_computed = self._compute_pcr_digest(pcr_values)
            # Compare pcrDigest extracted from the TPMS_ATTEST struct (not a substring scan)
            if pcr_digest_from_quote != pcr_digest_computed:
                raise QuoteVerificationError(
                    "PCR digest in TPMS_ATTEST does not match supplied pcr_values"
                )

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
            # CNSA 2.0 §2.1: minimum RSA key size for signatures is 3072 bits
            if key.key_size < 3072:
                raise QuoteVerificationError(
                    f"AK RSA key size {key.key_size} is below CNSA 2.0 minimum of 3072"
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
                # CNSA 2.0: RSA-PSS with SHA-384; PKCS1v15 not acceptable
                ak_pub.verify(
                    sig, data,
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA384()),
                        salt_length=padding.PSS.MAX_LENGTH,
                    ),
                    hashes.SHA384(),
                )
        except InvalidSignature as exc:
            raise QuoteVerificationError("AK signature verification failed") from exc

    @staticmethod
    def _read_tpm2b(buf: bytes, offset: int) -> tuple[bytes, int]:
        """Read a TPM2B (2-byte big-endian length + data) from buf at offset.

        Returns (data_bytes, new_offset).  Raises QuoteVerificationError on
        bounds violations rather than propagating struct.error.
        """
        if offset + 2 > len(buf):
            raise QuoteVerificationError(
                f"TPMS_ATTEST truncated reading TPM2B length at offset {offset}"
            )
        try:
            length, = struct.unpack_from(">H", buf, offset)
        except struct.error as exc:
            raise QuoteVerificationError(f"TPMS_ATTEST struct error at offset {offset}: {exc}") from exc
        offset += 2
        if offset + length > len(buf):
            raise QuoteVerificationError(
                f"TPMS_ATTEST truncated reading {length} bytes of TPM2B data at offset {offset}"
            )
        return buf[offset: offset + length], offset + length

    @staticmethod
    def _parse_and_validate_attest(quote_raw: bytes) -> bytes:
        """Parse TPMS_ATTEST and return qualifyingData bytes.

        Full layout (TPM2 spec Part 1 §10.12.8):
          UINT32 magic            — 0xFF544347
          UINT16 type             — 0x8018 (TPM_ST_ATTEST_QUOTE)
          TPM2B_NAME qualifiedSigner
          TPM2B_DATA qualifyingData   ← our nonce lives here
          TPMS_CLOCK_INFO (17 bytes: UINT64 clock + UINT32 resetCount +
                           UINT32 restartCount + UINT8 safe)
          UINT64 firmwareVersion
          TPMS_QUOTE_INFO attested:
            TPML_PCR_SELECTION pcrSelect:
              UINT32 count
              count × TPMS_PCR_SELECTION:
                UINT16 hash + UINT8 sizeofSelect + BYTE[sizeofSelect]
            TPM2B_DIGEST pcrDigest  ← extracted and returned
        """
        _MIN_HEADER = 6  # magic(4) + type(2)
        if len(quote_raw) < _MIN_HEADER:
            raise QuoteVerificationError("TPMS_ATTEST too short")

        offset = 0
        try:
            magic,    = struct.unpack_from(">I", quote_raw, offset); offset += 4  # noqa: E702
            tpm_type, = struct.unpack_from(">H", quote_raw, offset); offset += 2  # noqa: E702
        except struct.error as exc:
            raise QuoteVerificationError(f"TPMS_ATTEST header parse error: {exc}") from exc

        if magic != _TPM_GENERATED_VALUE:
            raise QuoteVerificationError(
                f"TPMS_ATTEST magic mismatch: expected {_TPM_GENERATED_VALUE:#010x}, got {magic:#010x}"
            )
        if tpm_type != _TPM_ST_ATTEST_QUOTE:
            raise QuoteVerificationError(
                f"TPMS_ATTEST type mismatch: expected {_TPM_ST_ATTEST_QUOTE:#06x}, got {tpm_type:#06x}"
            )

        # qualifiedSigner — skip
        _, offset = QuoteVerifier._read_tpm2b(quote_raw, offset)
        # qualifyingData — our nonce
        qualifying_data, offset = QuoteVerifier._read_tpm2b(quote_raw, offset)

        # clockInfo: UINT64 + UINT32 + UINT32 + UINT8 = 17 bytes
        # firmwareVersion: UINT64 = 8 bytes
        _SKIP = 17 + 8
        if offset + _SKIP > len(quote_raw):
            raise QuoteVerificationError("TPMS_ATTEST too short for clockInfo/firmwareVersion")
        offset += _SKIP

        # TPML_PCR_SELECTION.count (UINT32)
        if offset + 4 > len(quote_raw):
            raise QuoteVerificationError("TPMS_ATTEST truncated before pcrSelect count")
        try:
            pcr_select_count, = struct.unpack_from(">I", quote_raw, offset); offset += 4  # noqa: E702
        except struct.error as exc:
            raise QuoteVerificationError(f"TPMS_ATTEST pcrSelect count error: {exc}") from exc

        if pcr_select_count > 16:  # sanity check
            raise QuoteVerificationError(
                f"TPMS_ATTEST pcrSelect count {pcr_select_count} exceeds maximum 16"
            )

        # Skip each TPMS_PCR_SELECTION: UINT16 hash + UINT8 sizeofSelect + BYTE[sizeofSelect]
        for _ in range(pcr_select_count):
            if offset + 3 > len(quote_raw):
                raise QuoteVerificationError("TPMS_ATTEST truncated in TPMS_PCR_SELECTION")
            try:
                sizeof_select, = struct.unpack_from(">B", quote_raw, offset + 2)
            except struct.error as exc:
                raise QuoteVerificationError(f"TPMS_PCR_SELECTION parse error: {exc}") from exc
            offset += 3 + sizeof_select
            if offset > len(quote_raw):
                raise QuoteVerificationError("TPMS_ATTEST truncated after TPMS_PCR_SELECTION")

        # TPM2B_DIGEST pcrDigest — extract at exact offset
        pcrDigest, offset = QuoteVerifier._read_tpm2b(quote_raw, offset)  # noqa: F841

        return qualifying_data, pcrDigest

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
