#!/usr/bin/env python3
"""Tests for the post_repackaging_cleanup CLI module."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

MODULE = "truesight_dao_client.modules.post_repackaging_cleanup"


# ── Help output ───────────────────────────────────────────────────────────

class TestHelp:
    """UAT: --help prints canonical labels."""

    def test_cli_help(self):
        """--help exits 0 and lists all 14 canonical labels."""
        result = subprocess.run(
            [sys.executable, "-m", MODULE, "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        # Check for key canonical labels
        for label in ["Composition URL", "Holder Name", "Farm Name",
                      "State", "Country", "Year", "Landing Page",
                      "Ledger URL", "SKU Mapping", "Deplete Inputs",
                      "Add Output Locations", "Set Currencies Metadata",
                      "Rebuild Inventory", "Submission Source"]:
            assert label in result.stdout, f"Missing label: {label}"


# ── Dry-run ───────────────────────────────────────────────────────────────

class TestDryRun:
    """UAT U1: --dry-run prints signed share text without calling Edgar."""

    def test_cli_dry_run(self):
        """--dry-run with required fields prints share text and exits 0."""
        result = subprocess.run(
            [
                sys.executable, "-m", MODULE,
                "--composition-url", "https://example.com/composition.json",
                "--holder-name", "Kirsten Ritschel",
                "--dry-run",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Composition URL" in result.stdout
        assert "Holder Name" in result.stdout
        assert "Kirsten Ritschel" in result.stdout


# ── Missing required fields ───────────────────────────────────────────────

class TestMissingRequired:
    """UAT U2: Missing required fields exit with error."""

    def test_cli_missing_composition_url(self):
        """Missing --composition-url exits non-zero."""
        result = subprocess.run(
            [sys.executable, "-m", MODULE, "--holder-name", "Kirsten"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_cli_missing_holder_name(self):
        """Missing --holder-name exits non-zero."""
        result = subprocess.run(
            [sys.executable, "-m", MODULE,
             "--composition-url", "https://example.com/c.json"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_cli_missing_both(self):
        """Missing both required fields exits non-zero."""
        result = subprocess.run(
            [sys.executable, "-m", MODULE],
            capture_output=True, text=True,
        )
        assert result.returncode != 0


# ── All fields ────────────────────────────────────────────────────────────

class TestAllFields:
    """UAT U3: All 14 fields accepted."""

    def test_cli_all_fields(self):
        """All fields provided, dry-run prints them all."""
        result = subprocess.run(
            [
                sys.executable, "-m", MODULE,
                "--composition-url", "https://example.com/comp.json",
                "--holder-name", "Kirsten Ritschel",
                "--farm-name", "Fazenda Santa Clara",
                "--state", "Bahia",
                "--country", "Brazil",
                "--year", "2026",
                "--landing-page", "https://agroverse.com/shop",
                "--ledger-url", "https://ledger.truesight.me",
                "--sku-mapping", '{"Pouch": "ceremonial-cacao-pouch"}',
                "--deplete-inputs", "true",
                "--add-output-locations", "true",
                "--set-currencies-metadata", "true",
                "--rebuild-inventory", "false",
                "--dry-run",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Fazenda Santa Clara" in result.stdout
        assert "Bahia" in result.stdout
        assert "Brazil" in result.stdout
        assert "2026" in result.stdout
        assert "agroverse.com" in result.stdout
        assert "ceremonial-cacao-pouch" in result.stdout


# ── Defaults ──────────────────────────────────────────────────────────────

class TestDefaults:
    """UAT U4: Defaults applied when optional fields omitted."""

    def test_cli_defaults(self):
        """Only required fields: Deplete Inputs/Add Output/Set Currencies
        default to 'true', Rebuild Inventory defaults to 'false'."""
        result = subprocess.run(
            [
                sys.executable, "-m", MODULE,
                "--composition-url", "https://example.com/comp.json",
                "--holder-name", "Kirsten Ritschel",
                "--dry-run",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Deplete Inputs: true" in result.stdout or '"Deplete Inputs": "true"' in result.stdout
        assert "Add Output Locations: true" in result.stdout or '"Add Output Locations": "true"' in result.stdout
        assert "Set Currencies Metadata: true" in result.stdout or '"Set Currencies Metadata": "true"' in result.stdout
        assert "Rebuild Inventory: false" in result.stdout or '"Rebuild Inventory": "false"' in result.stdout


# ── SKU Mapping JSON ──────────────────────────────────────────────────────

class TestSkuMapping:
    """UAT U5: SKU Mapping JSON string accepted."""

    def test_cli_sku_mapping_json(self):
        """Valid JSON SKU Mapping is accepted."""
        sku = '{"Ceremonial Cacao Kraft Pouch": "ceremonial-cacao-kraft-pouch-200g"}'
        result = subprocess.run(
            [
                sys.executable, "-m", MODULE,
                "--composition-url", "https://example.com/comp.json",
                "--holder-name", "Kirsten",
                "--sku-mapping", sku,
                "--dry-run",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "ceremonial-cacao-kraft-pouch-200g" in result.stdout


# ── Invalid URL validation ────────────────────────────────────────────────

class TestInvalidUrl:
    """UAT U6: Invalid URLs rejected."""

    def test_cli_invalid_landing_page(self):
        """Invalid Landing Page URL exits non-zero."""
        result = subprocess.run(
            [
                sys.executable, "-m", MODULE,
                "--composition-url", "https://example.com/comp.json",
                "--holder-name", "Kirsten",
                "--landing-page", "not-a-url",
                "--dry-run",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_cli_invalid_ledger_url(self):
        """Invalid Ledger URL exits non-zero."""
        result = subprocess.run(
            [
                sys.executable, "-m", MODULE,
                "--composition-url", "https://example.com/comp.json",
                "--holder-name", "Kirsten",
                "--ledger-url", "not-a-url",
                "--dry-run",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
