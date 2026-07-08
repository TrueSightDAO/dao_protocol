"""Port of the `/dao` attachment→GitHub upload (dao_controller). When a signed submission carries
an `attachment` file AND its text references a `github.com/<owner>/<repo>/blob|tree/<branch>/<path>`
URL, upload the bytes to that path via the GitHub contents API (GET to check existence → PUT to
create). Returns True if the file is now present (uploaded or already existed). Uses the PAT from
`DAO_PROTOCOL_GITHUB_PAT`; no PAT / no file / no URL → False (responds `fileUploadedToGithub:false`)."""

from __future__ import annotations

import base64
import logging
import re

import requests

from ..config import get_settings

logger = logging.getLogger("dao_protocol.github_upload")
_URL_RE = re.compile(r"https://github\.com/([^/]+)/([^/]+)/(?:blob|tree)/([^/]+)/(.+)")
_EVENT_RE = re.compile(r"\[([A-Z ]+?EVENT)\]")


def _event_type(text: str) -> str:
    m = _EVENT_RE.search(text or "")
    if m:
        return m.group(1).lower()
    return "file"


def upload_if_referenced(text: str, file_bytes: bytes | None, filename: str | None = None) -> bool:
    pat = get_settings().github_pat
    if not pat or not file_bytes:
        return False
    m = _URL_RE.search(text or "")
    if not m:
        return False
    owner, repo, branch, path = m.group(1), m.group(2), m.group(3), m.group(4).strip()
    # strip any trailing query/fragment from the captured path
    path = path.split("?")[0].split("#")[0]
    api = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    try:
        get = requests.get(api, headers=headers, timeout=30)
        if get.status_code == 200:
            return True  # already exists — treat as success (matches Rails)
        if get.status_code == 404:
            event_type = _event_type(text)
            commit_message = f"Upload {event_type} file: {path}\n\n{text}"
            put = requests.put(api, headers=headers, timeout=60, json={
                "message": commit_message,
                "content": base64.b64encode(file_bytes).decode("ascii"),
                "branch": branch,
            })
            if put.status_code in (200, 201):
                return True
            logger.warning("github upload PUT %s for %s/%s:%s", put.status_code, owner, repo, path)
            return False
        logger.warning("github contents GET %s for %s/%s:%s", get.status_code, owner, repo, path)
        return False
    except requests.RequestException as exc:
        logger.warning("github upload failed: %s", exc)
        return False
