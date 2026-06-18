#!/usr/bin/env python3
"""
EdgarClient — Python port of dapp/scripts/edgar_payload_helper.js.

Every DAO action (contribution, inventory, notarize, etc.) is an Edgar
`submit_contribution` POST carrying a canonical payload:

    [<EVENT NAME>]
    - Label: value
    - Label: value
    --------

    My Digital Signature: <base64 SPKI public key>

    Request Transaction ID: <base64 RSASSA-PKCS1-v1_5 / SHA-256 signature>

    This submission was generated using <generation source URL>

    Verify submission here: https://dapp.truesight.me/verify_request.html

This module centralises key generation, payload construction, signing, and the
multipart POST so every per-module wrapper stays thin.
"""
from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from dotenv import load_dotenv, set_key

DEFAULT_EDGAR_BASE = "https://edgar.truesight.me"
DEFAULT_GENERATION_SOURCE = "https://dapp.truesight.me/create_signature.html"
DEFAULT_VERIFY_URL = "https://dapp.truesight.me/verify_request.html"


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def generate_keypair() -> tuple[str, str]:
    """Returns (public_spki_b64, private_pkcs8_b64) matching WebCrypto exportKey output."""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_der = priv.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_der = priv.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return _b64encode(pub_der), _b64encode(priv_der)


def load_private_key(private_b64: str) -> rsa.RSAPrivateKey:
    return serialization.load_der_private_key(base64.b64decode(private_b64), password=None)


def load_public_key(public_b64: str):
    return serialization.load_der_public_key(base64.b64decode(public_b64))


def format_attributes(attributes: Mapping[str, object] | Iterable[tuple[str, object]]) -> list[tuple[str, str]]:
    if isinstance(attributes, Mapping):
        items = list(attributes.items())
    else:
        items = list(attributes)
    out: list[tuple[str, str]] = []
    for label, raw in items:
        if raw is None:
            value = "N/A"
        elif isinstance(raw, (list, tuple)):
            value = ", ".join(str(v) for v in raw)
        else:
            value = str(raw)
        out.append((str(label), value))
    return out


def build_payload(event_name: str, attributes: Mapping[str, object] | Iterable[tuple[str, object]]) -> str:
    """Mirror EdgarPayloadHelper.buildPayloadString (JS)."""
    if not event_name:
        raise ValueError("event_name is required")
    lines: list[str] = []
    for label, value in format_attributes(attributes):
        if "\n" in value:
            value = value.replace("\r\n", "\n").replace("\n", "\n  ")
        lines.append(f"- {label}: {value}")
    return f"[{event_name.strip()}]\n" + "\n".join(lines) + "\n--------"


def sign_payload(private_key: rsa.RSAPrivateKey, payload: str) -> str:
    sig = private_key.sign(payload.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return _b64encode(sig)


def verify_signature(public_b64: str, payload: str, request_txn_id: str) -> bool:
    try:
        load_public_key(public_b64).verify(
            base64.b64decode(request_txn_id),
            payload.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


def build_share_text(
    payload: str,
    request_txn_id: str,
    public_key_b64: str,
    generation_source: str,
    verify_url: str = DEFAULT_VERIFY_URL,
) -> str:
    return (
        f"{payload}\n\n"
        f"My Digital Signature: {public_key_b64}\n\n"
        f"Request Transaction ID: {request_txn_id}\n\n"
        f"This submission was generated using {generation_source}\n\n"
        f"Verify submission here: {verify_url}"
    )


@dataclass
class EdgarClient:
    email: str
    public_key_b64: str
    private_key_b64: str
    generation_source: str = DEFAULT_GENERATION_SOURCE
    base_url: str = DEFAULT_EDGAR_BASE
    verify_url: str = DEFAULT_VERIFY_URL
    session: requests.Session = field(default_factory=requests.Session)

    # ------------------------------------------------------------------ env IO

    @classmethod
    def env_path(cls, path: Path | str | None = None) -> Path:
        if path is not None:
            return Path(path)
        # Default to CWD so `pip install` users and repo checkouts both pick up ./.env
        return Path.cwd() / ".env"

    @classmethod
    def from_env(
        cls,
        path: Path | str | None = None,
        *,
        generation_source: str = DEFAULT_GENERATION_SOURCE,
        base_url: str = DEFAULT_EDGAR_BASE,
    ) -> "EdgarClient":
        env = cls.env_path(path)
        load_dotenv(env)
        email = os.getenv("EMAIL", "").strip()
        pub = os.getenv("PUBLIC_KEY", "").strip()
        priv = os.getenv("PRIVATE_KEY", "").strip()
        if not email or not pub or not priv:
            raise RuntimeError(
                f"Missing EMAIL / PUBLIC_KEY / PRIVATE_KEY in {env}. "
                "Run `truesight-dao-auth login --email you@example.com` (or `python -m truesight_dao_client.auth login`) to initialise."
            )
        return cls(
            email=email,
            public_key_b64=pub,
            private_key_b64=priv,
            generation_source=generation_source,
            base_url=base_url,
        )

    @classmethod
    def write_env(
        cls,
        email: str,
        public_key_b64: str,
        private_key_b64: str,
        path: Path | str | None = None,
    ) -> Path:
        env = cls.env_path(path)
        if not env.exists():
            env.touch(mode=0o600)
        set_key(str(env), "EMAIL", email, quote_mode="never")
        set_key(str(env), "PUBLIC_KEY", public_key_b64, quote_mode="never")
        set_key(str(env), "PRIVATE_KEY", private_key_b64, quote_mode="never")
        env.chmod(0o600)
        return env

    # ------------------------------------------------------------- payload API

    def sign(self, event_name: str, attributes: Mapping[str, object]) -> tuple[str, str, str]:
        """Returns (payload, request_txn_id, share_text)."""
        payload = build_payload(event_name, attributes)
        request_txn_id = sign_payload(load_private_key(self.private_key_b64), payload)
        # Self-check: the JS client skips this but it costs microseconds and catches bad inputs fast.
        assert verify_signature(self.public_key_b64, payload, request_txn_id), "local signature verify failed"
        share_text = build_share_text(
            payload,
            request_txn_id,
            self.public_key_b64,
            self.generation_source,
            self.verify_url,
        )
        return payload, request_txn_id, share_text

    # ----------------------------------------------------------- network I/O

    def submit(
        self,
        event_name: str,
        attributes: Mapping[str, object],
        *,
        timeout: float = 30.0,
        attached_file_path: str | None = None,
    ) -> requests.Response:
        """Submit a signed event to Edgar.

        When ``attached_file_path`` is provided, the file bytes are sent as the
        ``attachment`` multipart field. Edgar's controller scans the signed text
        for a ``https://github.com/.../(blob|tree)/.../...`` URL and uploads the
        attachment bytes to that GitHub location via the Contents API. Caller
        is responsible for putting the destination URL into the event payload
        (typically as ``Destination Contribution File Location: <URL>``).

        This is the canonical pattern for proof-of-work attachments — dao_client
        does **not** push directly to GitHub; Edgar holds the GitHub PAT and
        does the upload server-side.
        """
        _, _, share_text = self.sign(event_name, attributes)
        files: dict[str, object] = {"text": (None, share_text)}
        if attached_file_path:
            import os
            from pathlib import Path
            p = Path(attached_file_path)
            if not p.is_file():
                raise FileNotFoundError(f"Attached file not found: {attached_file_path}")
            files["attachment"] = (p.name, p.read_bytes())
        return self.session.post(
            f"{self.base_url}/dao/submit_contribution",
            files=files,
            timeout=timeout,
        )

    def check_signature(self, timeout: float = 20.0) -> requests.Response:
        return self.session.get(
            f"{self.base_url}/dao/check_digital_signature",
            params={"signature": self.public_key_b64},
            timeout=timeout,
        )


# ------------------------------------------------------------- CLI scaffolding


ATTACHMENT_REPO_BASE_URL = "https://github.com/TrueSightDAO/.github/tree/main/assets/"
_ATTACHED_FILENAME_LABEL = "Attached Filename"
_DESTINATION_LABEL_RE = re.compile(r"^Destination .* File Location$")


def _derive_event_filename_prefix(event_name: str) -> str:
    """``CAPITAL INJECTION EVENT`` → ``capital_injection``."""
    name = (event_name or "").upper().strip()
    if name.endswith(" EVENT"):
        name = name[: -len(" EVENT")]
    return name.lower().replace(" ", "_") or "event"


def _sanitize_filename_part(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9.]", "_", (value or "")).strip("_").lower() or "unknown"


def _sanitize_contributor_part(email: str) -> str:
    local = (email or "").split("@", 1)[0]
    return _sanitize_filename_part(local)


def _generate_attachment_filename(event_name: str, contributor_email: str, original_filename: str) -> str:
    """Mirror the dapp filename pattern so the assets bucket stays consistent.

    Examples:
        contribution_20260520213412_garyjob_capture.png
        capital_injection_20260520213412_garyjob_receipt_5y1992.pdf
    """
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return "{prefix}_{ts}_{contrib}_{name}".format(
        prefix=_derive_event_filename_prefix(event_name),
        ts=timestamp,
        contrib=_sanitize_contributor_part(contributor_email),
        name=_sanitize_filename_part(original_filename),
    )


def _find_destination_label(labels: list[str]) -> str | None:
    for lbl in labels or []:
        if _DESTINATION_LABEL_RE.match(lbl):
            return lbl
    return None


def build_event_cli(
    *,
    event_name: str,
    canonical_labels: list[str] | None = None,
    dapp_page: str | None = None,
    validators: dict[str, callable] | None = None,
    normalizers: dict[str, callable] | None = None,
    defaults: dict[str, str] | None = None,
    required_labels: list[str] | None = None,
):
    """Returns a `main()` entry point that:
      1. Accepts repeated `--attr "Label=Value"` args.
      2. Also accepts each canonical label as `--snake-case-label VALUE` for ergonomics.
      3. Loads EdgarClient from .env and submits `event_name` with the collected attributes.

    Used by every file in `modules/` so each one becomes a ~6-line wrapper.
    """
    import argparse
    import json

    labels = list(canonical_labels or [])
    label_to_flag = {lbl: "--" + lbl.lower().replace("(", "").replace(")", "").replace(" ", "-") for lbl in labels}

    def main(argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser(
            description=(
                f"Submit [{event_name}] to Edgar. "
                + (f"Browser equivalent: dapp.truesight.me/{dapp_page}. " if dapp_page else "")
                + "Use --attr 'Label=Value' for any label not exposed as a dedicated flag."
            ),
        )
        for lbl in labels:
            parser.add_argument(
                label_to_flag[lbl],
                dest=f"canon_{lbl}",
                default=None,
                metavar="VALUE",
                help=f'Sets "- {lbl}: ..." in the payload.',
            )
        parser.add_argument(
            "--attr",
            action="append",
            default=[],
            metavar="LABEL=VALUE",
            help='Add any attribute not covered by a named flag. Repeatable.',
        )
        parser.add_argument(
            "--generation-source",
            default=None,
            help='Override the "This submission was generated using ..." line.',
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the signed share text without hitting Edgar.",
        )
        parser.add_argument(
            "--attachment",
            default=None,
            metavar="FILE",
            help="Local file to attach (e.g. invoice PDF). Sent as multipart alongside the signed event. Edgar parses the Destination Contribution File Location URL in the text and uploads the file to GitHub.",
        )
        args = parser.parse_args(argv)

        # Apply defaults before collecting attrs so missing labels get their default value.
        _defaults = defaults or {}
        for lbl in labels:
            attr_name = f"canon_{lbl}"
            if getattr(args, attr_name) is None and lbl in _defaults:
                setattr(args, attr_name, _defaults[lbl])

        # Collect in label order: first the canonical labels that got values, then --attr extras.
        attrs: list[tuple[str, str]] = []
        for lbl in labels:
            val = getattr(args, f"canon_{lbl}")
            if val is not None:
                attrs.append((lbl, val))
        seen = {lbl for lbl, _ in attrs}
        for entry in args.attr:
            if "=" not in entry:
                parser.error(f"--attr expects LABEL=VALUE, got {entry!r}")
            lbl, val = entry.split("=", 1)
            lbl = lbl.strip()
            if lbl in seen:
                # Let --attr override the named flag if both were given.
                attrs = [(existing_lbl, existing_val) for existing_lbl, existing_val in attrs if existing_lbl != lbl]
            attrs.append((lbl, val))
            seen.add(lbl)

        # Validate required labels after --attr overrides have been applied.
        _required = required_labels or []
        missing = [lbl for lbl in _required if lbl not in seen]
        if missing:
            parser.error(f"Missing required field(s): {', '.join(missing)}")

        if not attrs:
            parser.error("At least one attribute is required (use --attr LABEL=VALUE or a named flag).")

        normalized_attrs: list[tuple[str, str]] = []
        for lbl, val in attrs:
            if validators and lbl in validators:
                try:
                    validators[lbl](val)
                except ValueError as exc:
                    parser.error(str(exc))
            if normalizers and lbl in normalizers:
                val = normalizers[lbl](val)
            normalized_attrs.append((lbl, val))

        client = EdgarClient.from_env()
        if args.generation_source:
            client.generation_source = args.generation_source

        # ─── Attachment auto-fill ─────────────────────────────────────
        # Mirrors dapp/report_contribution.html behaviour: when an
        # --attachment is provided but the operator didn't explicitly set
        # the Attached Filename / Destination ... File Location labels,
        # auto-generate them so Edgar knows where to commit the file.
        # Without these labels in the payload, Edgar receives the bytes
        # but returns fileUploadedToGithub:false (silent failure mode).
        if args.attachment:
            seen_labels = {lbl for lbl, _ in normalized_attrs}
            original_filename = Path(args.attachment).name
            if _ATTACHED_FILENAME_LABEL in seen_labels:
                generated_name = next(v for lbl, v in normalized_attrs if lbl == _ATTACHED_FILENAME_LABEL)
            else:
                generated_name = _generate_attachment_filename(event_name, client.email, original_filename)
                normalized_attrs.append((_ATTACHED_FILENAME_LABEL, generated_name))
                seen_labels.add(_ATTACHED_FILENAME_LABEL)

            destination_label = _find_destination_label(labels)
            if destination_label and destination_label not in seen_labels:
                normalized_attrs.append((destination_label, ATTACHMENT_REPO_BASE_URL + generated_name))

        if args.dry_run:
            payload, txn_id, share_text = client.sign(event_name, normalized_attrs)
            print(share_text)
            return 0

        resp = client.submit(event_name, normalized_attrs, attached_file_path=args.attachment)
        print(f"HTTP {resp.status_code}")
        try:
            data = resp.json()
            print(json.dumps(data, indent=2))
        except ValueError:
            print(resp.text)
        return 0 if resp.ok else 1

    return main


__all__ = [
    "DEFAULT_EDGAR_BASE",
    "DEFAULT_GENERATION_SOURCE",
    "DEFAULT_VERIFY_URL",
    "EdgarClient",
    "build_event_cli",
    "build_payload",
    "build_share_text",
    "generate_keypair",
    "load_private_key",
    "load_public_key",
    "sign_payload",
    "verify_signature",
]
