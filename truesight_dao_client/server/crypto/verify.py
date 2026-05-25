"""RSA signature verification — Python port of Rails ``SignatureVerifier.verify``.

The signed payload format (produced by `create_signature.html` / the dao_client signer):

    <event body lines…>
    --------
    My Digital Signature: <base64 SPKI public key>
    Request Transaction ID: <base64 RSASSA-PKCS1-v1_5 / SHA-256 signature>

Note the field-name swap (matches the Rails verifier and the HTML signer): the "My Digital
Signature" field carries the **public key**, and "Request Transaction ID" carries the
**signature**. The signed message is everything up to and including the `--------` separator,
`.strip()`-ed. Uses `cryptography` (already a package dependency — same lib `edgar_client.py`
signs with), so verify and sign share one crypto stack.
"""

from __future__ import annotations

import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

SEPARATOR = "--------"
_SIG_HDR = "My Digital Signature: "
_TXN_HDR = "Request Transaction ID: "


class VerificationError(ValueError):
    """Raised on malformed input or an unloadable key/signature (mirrors the Rails
    ArgumentError). A *valid-format-but-wrong* signature is NOT an error — it returns
    ``{"success": False}``."""


def _value_after_header(lines: list[str], idx: int, header: str) -> str:
    line = lines[idx]
    if len(line) > len(header):
        return line[len(header):].strip()
    return (lines[idx + 1].strip() if idx + 1 < len(lines) else "")


def verify(input_text: str) -> dict:
    normalized = (input_text or "").replace("\r\n", "\n")
    lines = normalized.split("\n")

    separator_index = next((i for i, ln in enumerate(lines) if ln.strip() == SEPARATOR), -1)
    if separator_index == -1:
        raise VerificationError(
            "Could not find the content separator (--------). "
            "Make sure the request format is correct."
        )

    message = "\n".join(lines[: separator_index + 1])

    signature_start = transaction_start = -1
    for i in range(separator_index + 1, len(lines)):
        if lines[i].startswith(_SIG_HDR):
            signature_start = i
        elif lines[i].startswith(_TXN_HDR):
            transaction_start = i
            break
    if signature_start == -1 or transaction_start == -1:
        raise VerificationError(
            "We couldn't find the digital signature or transaction ID in the request. "
            'Make sure they start with "My Digital Signature:" and "Request Transaction ID:".'
        )

    public_key_pem = _value_after_header(lines, signature_start, _SIG_HDR)
    signature_base64 = _value_after_header(lines, transaction_start, _TXN_HDR)

    if SEPARATOR not in message:
        raise VerificationError('Invalid message format: Must end with "--------".')
    message_to_sign = message.strip()

    if not public_key_pem.startswith("-----BEGIN PUBLIC KEY-----"):
        public_key_pem = f"-----BEGIN PUBLIC KEY-----\n{public_key_pem}\n-----END PUBLIC KEY-----"

    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        signature = base64.b64decode(signature_base64)
    except Exception as exc:  # bad key PEM or bad base64 → hard error (like Rails)
        raise VerificationError(f"Signature verification failed: invalid key/signature format - {exc}")

    result = {
        "payload": message_to_sign,
        "signature": signature_base64,
        "public_key": public_key_pem,
    }
    try:
        public_key.verify(
            signature,
            message_to_sign.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return {**result, "success": True, "message": "Signature verification successful"}
    except InvalidSignature:
        return {
            **result,
            "success": False,
            "message": "Signature verification failed - payload does not match when "
                       "decrypted with digital signature",
        }
