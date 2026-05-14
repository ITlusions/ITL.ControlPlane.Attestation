"""Re-export shim — actual implementation lives in pki/tpm_verifier.py."""
from .pki.tpm_verifier import (  # noqa: F401
    decode_pem,
    verify_ek_pem,
    compute_ek_fingerprint,
    fingerprints_match,
    load_ek_public_key,
)

