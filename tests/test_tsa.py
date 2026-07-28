"""Tests for tradememory.audit.tsa — RFC 3161 TimeStampReq construction
and round-trip behaviour against a mocked TSA endpoint.

We do not hit the network in tests. Live TSA submission (freetsa.org) is
exercised by `scripts/smoke_tsa.py` if you want to verify end-to-end.
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from tradememory.audit.tsa import (
    DEFAULT_TSA_URL,
    TSAError,
    build_tsq,
    parse_status_from_tsr,
    request_timestamp,
)


# ---------------------------------------------------------------------------
# TimeStampReq construction
# ---------------------------------------------------------------------------

VALID_SHA256_HEX = "a05544ca4a8bda9bb7862668be3b142dc346a47a5016e0af46209ab754301d85"


def test_build_tsq_starts_with_sequence_tag():
    der, _ = build_tsq(VALID_SHA256_HEX, nonce=42)
    assert der[0] == 0x30  # outer SEQUENCE


def test_build_tsq_contains_digest_bytes():
    der, _ = build_tsq(VALID_SHA256_HEX, nonce=42)
    assert bytes.fromhex(VALID_SHA256_HEX) in der


def test_build_tsq_contains_sha256_oid():
    der, _ = build_tsq(VALID_SHA256_HEX, nonce=42)
    # 06 09 60 86 48 01 65 03 04 02 01 == SHA-256 OID
    assert bytes.fromhex("0609608648016503040201") in der


def test_build_tsq_rejects_wrong_length_hex():
    with pytest.raises(ValueError):
        build_tsq("00" * 16, nonce=1)  # too short


def test_build_tsq_nonce_returned():
    _, nonce = build_tsq(VALID_SHA256_HEX, nonce=12345)
    assert nonce == 12345


def test_build_tsq_random_nonce_when_unspecified():
    _, n1 = build_tsq(VALID_SHA256_HEX)
    _, n2 = build_tsq(VALID_SHA256_HEX)
    assert n1 != n2
    assert n1 > 0 and n2 > 0


def test_build_tsq_cert_req_flag_in_payload():
    # certReq TRUE
    der_true, _ = build_tsq(VALID_SHA256_HEX, nonce=1, cert_req=True)
    # certReq FALSE
    der_false, _ = build_tsq(VALID_SHA256_HEX, nonce=1, cert_req=False)
    assert der_true != der_false


# ---------------------------------------------------------------------------
# Network round-trip (mocked)
# ---------------------------------------------------------------------------

class _MockResponse:
    """Minimal stand-in for urllib's response context manager."""

    def __init__(self, status: int, body: bytes, content_type: str = "application/timestamp-reply"):
        self.status = status
        self._body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self._body


# A DER SEQUENCE prefix (0x30 + len) — enough for our content-type check.
_FAKE_TSR = b"\x30\x82\x00\x10" + b"\x00" * 16

# Minimal parseable TimeStampResp: SEQUENCE { SEQUENCE { INTEGER status } }
_TSR_GRANTED = bytes.fromhex("30053003020100")   # PKIStatus = 0
_TSR_REJECTED = bytes.fromhex("30053003020102")  # PKIStatus = 2 (rejection)


def test_request_timestamp_success_returns_response():
    with patch("urllib.request.urlopen", return_value=_MockResponse(200, _FAKE_TSR)):
        resp = request_timestamp(VALID_SHA256_HEX, nonce=99)
    assert resp.response_der == _FAKE_TSR
    assert resp.nonce == 99
    assert resp.sha256_hex == VALID_SHA256_HEX
    assert resp.tsa_url == DEFAULT_TSA_URL


def test_request_timestamp_accepts_granted_status():
    with patch("urllib.request.urlopen", return_value=_MockResponse(200, _TSR_GRANTED)):
        resp = request_timestamp(VALID_SHA256_HEX, nonce=1)
    assert resp.response_der == _TSR_GRANTED


def test_request_timestamp_raises_on_rejected_status():
    """A TSA rejection (PKIStatus=2) must never be stored as an anchor."""
    with patch("urllib.request.urlopen", return_value=_MockResponse(200, _TSR_REJECTED)):
        with pytest.raises(TSAError, match="PKIStatus=2"):
            request_timestamp(VALID_SHA256_HEX, nonce=1)


def test_request_timestamp_uses_env_url():
    custom = "https://example.tsa/tsr"
    with patch.dict("os.environ", {"TRADEMEMORY_TSA_URL": custom}):
        with patch(
            "urllib.request.urlopen", return_value=_MockResponse(200, _FAKE_TSR)
        ) as mock_open:
            request_timestamp(VALID_SHA256_HEX, nonce=1)
        called_request = mock_open.call_args[0][0]
        assert called_request.full_url == custom


def test_request_timestamp_raises_on_500():
    with patch("urllib.request.urlopen", return_value=_MockResponse(500, b"oops")):
        with pytest.raises(TSAError):
            request_timestamp(VALID_SHA256_HEX, nonce=1)


def test_request_timestamp_raises_on_non_der_body():
    bad = b"<html>error</html>"
    with patch("urllib.request.urlopen", return_value=_MockResponse(200, bad)):
        with pytest.raises(TSAError):
            request_timestamp(VALID_SHA256_HEX, nonce=1)


def test_request_timestamp_raises_on_network_error():
    import urllib.error
    err = urllib.error.URLError("connection refused")
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(TSAError):
            request_timestamp(VALID_SHA256_HEX, nonce=1)


def test_request_timestamp_accepts_loose_content_type():
    # Some TSAs return generic content-types; as long as body is DER, accept.
    resp_obj = _MockResponse(200, _FAKE_TSR, content_type="application/octet-stream")
    with patch("urllib.request.urlopen", return_value=resp_obj):
        resp = request_timestamp(VALID_SHA256_HEX, nonce=1)
    assert resp.response_der == _FAKE_TSR


# ---------------------------------------------------------------------------
# PKIStatus parsing
# ---------------------------------------------------------------------------

def test_parse_status_returns_none_on_garbage():
    assert parse_status_from_tsr(b"not der") is None
    assert parse_status_from_tsr(b"") is None


def test_parse_status_extracts_zero_granted():
    # Minimal TimeStampResp with PKIStatus=0 (granted):
    # SEQUENCE { SEQUENCE { INTEGER 0 } }
    tsr = bytes.fromhex("30053003020100")
    assert parse_status_from_tsr(tsr) == 0


def test_parse_status_extracts_one_granted_with_mods():
    tsr = bytes.fromhex("30053003020101")
    assert parse_status_from_tsr(tsr) == 1


# ---------------------------------------------------------------------------
# ChainBuilder integration — TSA failure is non-fatal
# ---------------------------------------------------------------------------

def test_build_daily_root_with_tsa_failure_still_persists_root(tmp_path):
    """If TSA submission fails, the chain still gets a (token-less) root."""
    from tradememory.audit.chain import ChainBuilder, GENESIS_HASH, chained_hash
    from tradememory.db import Database

    db = Database(str(tmp_path / "tm.db"))
    # Manually insert a chain entry on a specific day.
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    content = "ab" * 32
    dh = chained_hash(GENESIS_HASH, content)
    conn.execute(
        "INSERT INTO audit_chain (record_id, sequence_num, content_hash, "
        "prev_hash, data_hash, chained_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("rec-1", 1, content, GENESIS_HASH, dh, "2026-05-14T12:00:00+00:00"),
    )
    conn.commit()

    # Force TSA to fail.
    with patch(
        "tradememory.audit.tsa.request_timestamp",
        side_effect=TSAError("simulated"),
    ):
        root = ChainBuilder(conn).build_daily_root(
            "2026-05-14", request_tsa=True
        )
    conn.commit()

    # Root is built; tsa_token is NULL.
    assert root.record_count == 1
    row = conn.execute(
        "SELECT tsa_token FROM audit_roots WHERE period_start = ?",
        (root.period_start,),
    ).fetchone()
    assert row["tsa_token"] is None
    conn.close()


def test_build_daily_root_with_tsa_success_stores_token(tmp_path):
    from tradememory.audit.chain import ChainBuilder, GENESIS_HASH, chained_hash
    from tradememory.audit.tsa import TSAResponse
    from tradememory.db import Database
    import sqlite3

    db = Database(str(tmp_path / "tm.db"))
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    content = "cd" * 32
    dh = chained_hash(GENESIS_HASH, content)
    conn.execute(
        "INSERT INTO audit_chain (record_id, sequence_num, content_hash, "
        "prev_hash, data_hash, chained_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("rec-2", 1, content, GENESIS_HASH, dh, "2026-05-14T12:00:00+00:00"),
    )
    conn.commit()

    fake_token = b"\x30\x82\x00\x10" + b"\x42" * 16

    def _fake_request(sha256_hex, **kwargs):
        return TSAResponse(
            tsa_url="https://fake.tsa",
            request_der=b"",
            response_der=fake_token,
            nonce=1,
            sha256_hex=sha256_hex.lower(),
        )

    with patch(
        "tradememory.audit.tsa.request_timestamp", side_effect=_fake_request
    ):
        root = ChainBuilder(conn).build_daily_root(
            "2026-05-14", request_tsa=True
        )
    conn.commit()

    row = conn.execute(
        "SELECT tsa_token FROM audit_roots WHERE period_start = ?",
        (root.period_start,),
    ).fetchone()
    assert row["tsa_token"] == fake_token
    conn.close()
