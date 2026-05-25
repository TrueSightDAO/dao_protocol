"""Tests for server/crypto/verify.py (PR5a). Uses the real known-good payload from the Rails
SignatureVerifier.test_example_payload — proves byte-exact message reconstruction + RSA verify."""

from __future__ import annotations

import pytest

from truesight_dao_client.server.crypto import verify as v

# Verbatim from Rails SignatureVerifier.test_example_payload (real public key + signature).
GOOD_PAYLOAD = """[VOTING RIGHTS WITHDRAWAL REQUEST]
amount to withdraw: 70
asking price: 90
--------

My Digital Signature: MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0D70xOu3BmuhnWJ5sAXdmJyglssswFUqcjjESrwdEeygjXkQaMcckbW4dt4Q6CmlHUKPshMDfy8Zrp+hVvr6WE6oC4cZe/faL20xNCmS0wos8w+USdvoGbvEC6yMop6XGR3r29fDwK1JohrXXrMpPYT3KYM6NlVvBnjOEejvOg0H1tWxwVXSMPwxfrPDJbfpY7oI+mK+lPbVsnuilKH7GCMTQMG1wlwo69nan5uIahtYl5WYCt7SuOYe91ziryNtJSweZK+9Vxv6k5oyopPxTZ+r5EMIneT0jsOZR7svp5rpSuEOP+1KSZ2dpHqgKw+OoGUXHbs0ANJwriV8erOAywIDAQAB

Request Transaction ID: PV0ZZI3FKJJPqjfaqWltHPgmka+pWfFkNnXlTILNNOnpp9hrlewy7SMHlA1mqAPmo+r+WP2klbJTBxys871CG7kDcehJWN59awrRCzKF6AIuSzfq2T/PfVgufIJoZuDYD4FZgD3Z6nnpnuiBUCSW0vHQm9DnimRcZwQOyGAjMUHOKHglrtO6l1Y7J9oftkotXAjO7VceUoUKNgdCTrr8hoQL68Pd2p6ImazyPWgW+KKK3QGUrv0wOnqI/BE7rHC0G/VnOh6TwdA+PLGszXg74HizMTq4q4ELw1TllT6NExeaV4kYDyPr1fK1xYSa8lrpiTJ1cwE3BP94txrs2pBMrQ==
"""


def test_valid_signature_succeeds():
    result = v.verify(GOOD_PAYLOAD)
    assert result["success"] is True
    assert result["message"] == "Signature verification successful"
    assert result["payload"].startswith("[VOTING RIGHTS WITHDRAWAL REQUEST]")
    assert result["payload"].endswith("--------")


def test_tampered_body_fails_cleanly():
    tampered = GOOD_PAYLOAD.replace("amount to withdraw: 70", "amount to withdraw: 700")
    result = v.verify(tampered)
    assert result["success"] is False
    assert "does not match" in result["message"]


def test_missing_separator_raises():
    with pytest.raises(v.VerificationError):
        v.verify("[SOME EVENT]\nno separator here\nMy Digital Signature: x\nRequest Transaction ID: y")


def test_missing_signature_headers_raises():
    with pytest.raises(v.VerificationError):
        v.verify("[SOME EVENT]\nbody\n--------\n(no signature headers)")


def test_bad_key_material_raises():
    bad = "[X]\nbody\n--------\nMy Digital Signature: not-base64-key\nRequest Transaction ID: AAAA"
    with pytest.raises(v.VerificationError):
        v.verify(bad)
