#!/usr/bin/env python3
"""Tests for the define_currency CLI module ([CURRENCY DEFINITION EVENT]).

Covers the SKU-backed additions (col M `SKU Product ID`) and the `year_value`
validator fix (`--year 2026` must be accepted, not mistaken for a date).
"""

import base64
import os
import subprocess
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

MODULE = "truesight_dao_client.modules.define_currency"


def _throwaway_env():
    """Hermetic env: a throwaway RSA keypair so EdgarClient.from_env() succeeds
    in a clean CI checkout (no ~/.env). Mirrors `truesight-dao-auth login` output."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = base64.b64encode(
        key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode()
    priv = base64.b64encode(
        key.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    ).decode()
    env = dict(os.environ)
    env.update({"EMAIL": "test@example.com", "PUBLIC_KEY": pub, "PRIVATE_KEY": priv})
    return env


def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", MODULE, *args],
        capture_output=True, text=True, env=_throwaway_env(),
    )


class TestHelp:
    def test_cli_help_lists_all_13_labels(self):
        result = _run("--help")
        assert result.returncode == 0
        for label in [
            "Currency", "Price in USD", "Serializable", "Product Image",
            "Landing Page", "Ledger", "Farm Name", "State", "Country",
            "Year", "Unit Weight (grams)", "Unit Weight (ounces)",
            "SKU Product ID",
        ]:
            assert label in result.stdout, f"Missing label: {label}"
        # browser equivalent now points at the DApp page
        assert "define_currency.html" in result.stdout


class TestDryRun:
    def test_dry_run_renders_sku_product_id_label(self):
        result = _run("--currency", "Ceremonial Cacao (250g)",
             "--sku-product-id", "oscar-bahia-ceremonial-cacao-200g",
             "--price", "25.00",
             "--year", "2026",
             "--dry-run")
        assert result.returncode == 0, result.stderr
        assert "- Currency: Ceremonial Cacao (250g)" in result.stdout
        assert "- SKU Product ID: oscar-bahia-ceremonial-cacao-200g" in result.stdout
        assert "- Price in USD: 25.00" in result.stdout
        # Serializable defaulted to TRUE
        assert "- Serializable: TRUE" in result.stdout
        assert "- Year: 2026" in result.stdout


class TestYearValidator:
    def test_four_digit_year_accepted(self):
        result = _run("--currency", "X", "--year", "2026", "--dry-run")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "- Year: 2026" in result.stdout

    def test_full_date_year_rejected(self):
        result = _run("--currency", "X", "--year", "20260101", "--dry-run")
        assert result.returncode != 0
        assert "4-digit year" in (result.stdout + result.stderr)


class TestRequiredCurrency:
    def test_missing_currency_errors(self):
        result = _run("--price", "25", "--dry-run")
        assert result.returncode != 0
        assert "Missing required field" in (result.stdout + result.stderr)


class TestOptionalWeights:
    def test_weights_optional(self):
        result = _run("--currency", "X", "--dry-run")
        assert result.returncode == 0, result.stderr
        assert "- Currency: X" in result.stdout
