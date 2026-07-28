"""RFC 3161 Time-Stamp Protocol (TSP) client.

Submits an audit_root hash to a public Time Stamp Authority (TSA) and stores
the returned TimeStampToken (TST) as a DER-encoded blob.

The TST is the TSA's signed assertion: "I (the TSA) saw this hash at this
UTC instant." Anyone can later verify the TST against the TSA's published
certificate to prove the audit chain existed by that instant — without
trusting Mnemox's clock or storage.

Defaults to https://freetsa.org/ which is a community-run TSA — useful for
demonstrating capability but NOT legally qualified under eIDAS. Production
deployments should swap in a commercial qualified TSA (DigiCert, SwissSign,
GlobalSign, etc.) by setting `TRADEMEMORY_TSA_URL`.

Implementation notes
--------------------
We build the TimeStampReq manually to avoid an asn1 / pyOpenSSL dependency:

    TimeStampReq ::= SEQUENCE  {
       version            INTEGER  { v1(1) },
       messageImprint     MessageImprint,
       reqPolicy          TSAPolicyId      OPTIONAL,
       nonce              INTEGER          OPTIONAL,
       certReq            BOOLEAN          DEFAULT FALSE,
       extensions         [0] IMPLICIT Extensions OPTIONAL
    }

    MessageImprint ::= SEQUENCE  {
       hashAlgorithm      AlgorithmIdentifier,
       hashedMessage      OCTET STRING
    }

The DER for SHA-256 AlgorithmIdentifier is a well-known fixed prefix.
"""

from __future__ import annotations

import logging
import os
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


DEFAULT_TSA_URL = "https://freetsa.org/tsr"
TSA_URL_ENV = "TRADEMEMORY_TSA_URL"
TSA_ENABLED_ENV = "TRADEMEMORY_TSA"
TSA_TIMEOUT_SECONDS = 10


def tsa_enabled_by_default() -> bool:
    """Whether RFC 3161 timestamping is on when callers don't say otherwise.

    Defaults to ON (v0.5.3+): daily roots get an independent-time attestation
    unless the user opts out with TRADEMEMORY_TSA=off. This is the single
    documented exception to the local-first no-outbound-calls posture.
    """
    return os.environ.get(TSA_ENABLED_ENV, "on").strip().lower() not in (
        "off", "0", "false", "no",
    )

# DER-encoded AlgorithmIdentifier for SHA-256 (RFC 5754 / id-sha256
# 2.16.840.1.101.3.4.2.1) with NULL parameters omitted.
#   SEQUENCE { OID 2.16.840.1.101.3.4.2.1 }
_SHA256_OID_DER = bytes.fromhex("300d06096086480165030402010500")
# Breakdown:
#   30 0d                        SEQUENCE, 13 bytes
#     06 09 60 86 48 01 65 03 04 02 01    OID 2.16.840.1.101.3.4.2.1
#     05 00                                NULL


class TSAError(RuntimeError):
    """Raised when TSA submission fails irrecoverably."""


@dataclass(frozen=True)
class TSAResponse:
    """One TSA round-trip result."""

    tsa_url: str
    request_der: bytes
    response_der: bytes
    nonce: int
    sha256_hex: str


# ---------------------------------------------------------------------------
# Minimal DER helpers — just enough to build a TimeStampReq.
# ---------------------------------------------------------------------------

def _encode_length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    body = b""
    while n > 0:
        body = bytes([n & 0xFF]) + body
        n >>= 8
    return bytes([0x80 | len(body)]) + body


def _der_seq(*items: bytes) -> bytes:
    body = b"".join(items)
    return b"\x30" + _encode_length(len(body)) + body


def _der_int(n: int) -> bytes:
    if n == 0:
        body = b"\x00"
    else:
        length = (n.bit_length() + 8) // 8
        body = n.to_bytes(length, "big")
        if body[0] & 0x80:
            body = b"\x00" + body
    return b"\x02" + _encode_length(len(body)) + body


def _der_octet(b: bytes) -> bytes:
    return b"\x04" + _encode_length(len(b)) + b


def _der_bool(v: bool) -> bytes:
    return b"\x01\x01" + (b"\xff" if v else b"\x00")


def build_tsq(sha256_hex: str, nonce: Optional[int] = None,
              cert_req: bool = True) -> tuple[bytes, int]:
    """Build a TimeStampReq DER blob for a SHA-256 digest.

    Returns (der_bytes, nonce_used).
    """
    digest = bytes.fromhex(sha256_hex.lower())
    if len(digest) != 32:
        raise ValueError(
            f"sha256_hex must decode to 32 bytes, got {len(digest)}"
        )
    if nonce is None:
        # Random 63-bit non-zero positive integer (avoid sign-bit issues).
        nonce = secrets.randbits(63) | 1

    message_imprint = _der_seq(_SHA256_OID_DER, _der_octet(digest))
    parts = [
        _der_int(1),         # version
        message_imprint,     # messageImprint
        _der_int(nonce),     # nonce
        _der_bool(cert_req), # certReq
    ]
    return _der_seq(*parts), nonce


# ---------------------------------------------------------------------------
# Network round-trip
# ---------------------------------------------------------------------------

def request_timestamp(
    sha256_hex: str,
    tsa_url: Optional[str] = None,
    timeout: int = TSA_TIMEOUT_SECONDS,
    nonce: Optional[int] = None,
) -> TSAResponse:
    """POST a TimeStampReq to the configured TSA and return the response.

    Raises TSAError on network failure or non-200 status. Callers should
    treat TSA failures as non-fatal — the chain remains valid without
    a timestamp; the timestamp is an external attestation layer.

    Args:
        sha256_hex: 64-char hex SHA-256 digest (typically a Merkle root).
        tsa_url: Override TSA endpoint (default: $TRADEMEMORY_TSA_URL or freetsa.org).
        timeout: HTTP timeout in seconds.
        nonce: Optional fixed nonce (for deterministic tests). Default: random.
    """
    if tsa_url is None:
        tsa_url = os.environ.get(TSA_URL_ENV, DEFAULT_TSA_URL)

    tsq_der, nonce_used = build_tsq(sha256_hex, nonce=nonce)

    req = urllib.request.Request(
        tsa_url,
        data=tsq_der,
        headers={
            "Content-Type": "application/timestamp-query",
            "Content-Length": str(len(tsq_der)),
            # Some TSAs check User-Agent / Accept; be friendly.
            "Accept": "application/timestamp-reply",
            "User-Agent": "tradememory-protocol (+https://github.com/mnemox-ai/tradememory-protocol)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()
    except urllib.error.URLError as e:
        raise TSAError(f"TSA network failure: {e}") from e
    except Exception as e:  # noqa: BLE001 — propagate as TSAError for callers
        raise TSAError(f"TSA request error: {e}") from e

    if status != 200:
        raise TSAError(f"TSA HTTP {status} (body={body[:64]!r})")
    if "timestamp-reply" not in content_type:
        # Some TSAs are lax with content-type; log but don't reject if the
        # body decodes to a plausible TSR (starts with SEQUENCE 0x30).
        logger.warning(
            "TSA returned unexpected content-type %r; first bytes=%r",
            content_type, body[:8],
        )
    if not body or body[0] != 0x30:
        raise TSAError(
            f"TSA response is not a DER SEQUENCE (first byte={body[:1]!r})"
        )

    # A TimeStampResp with PKIStatus outside (0=granted, 1=grantedWithMods)
    # is an explicit rejection — storing it would fake an anchoring proof.
    # None (unparseable) stays best-effort: some TSAs return bare tokens.
    pki_status = parse_status_from_tsr(body)
    if pki_status is not None and pki_status not in (0, 1):
        raise TSAError(
            f"TSA rejected the request: PKIStatus={pki_status} "
            f"(expected 0=granted or 1=grantedWithMods)"
        )

    return TSAResponse(
        tsa_url=tsa_url,
        request_der=tsq_der,
        response_der=body,
        nonce=nonce_used,
        sha256_hex=sha256_hex.lower(),
    )


def parse_status_from_tsr(response_der: bytes) -> Optional[int]:
    """Extract the PKIStatus integer from a TimeStampResp, if present.

    A successful TSR has PKIStatus = 0 (granted) or 1 (grantedWithMods).
    Returns None if parsing fails — caller should treat as best-effort.

    TimeStampResp ::= SEQUENCE {
       status      PKIStatusInfo,
       timeStampToken TimeStampToken OPTIONAL
    }
    PKIStatusInfo ::= SEQUENCE { status PKIStatus, statusString..., failInfo... }
    """
    try:
        # SEQUENCE (TimeStampResp)
        if not response_der or response_der[0] != 0x30:
            return None
        # Skip outer SEQUENCE header.
        idx = 1
        idx, _ = _skip_length(response_der, idx)
        # Inner SEQUENCE (PKIStatusInfo)
        if response_der[idx] != 0x30:
            return None
        idx += 1
        idx, _ = _skip_length(response_der, idx)
        # First element: INTEGER (PKIStatus)
        if response_der[idx] != 0x02:
            return None
        idx += 1
        idx, status_len = _skip_length(response_der, idx)
        status_bytes = response_der[idx:idx + status_len]
        return int.from_bytes(status_bytes, "big", signed=False)
    except Exception:  # noqa: BLE001
        return None


def _skip_length(buf: bytes, idx: int) -> tuple[int, int]:
    """Return (new_idx, length) after consuming a DER length at buf[idx]."""
    first = buf[idx]
    idx += 1
    if first < 0x80:
        return idx, first
    n_bytes = first & 0x7F
    length = int.from_bytes(buf[idx:idx + n_bytes], "big")
    return idx + n_bytes, length
