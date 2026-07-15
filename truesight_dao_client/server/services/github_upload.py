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
    path = path.split("?")[0].split("#")[0]
    return _put_file(pat, owner, repo, branch, path, file_bytes, filename, text)


def _put_file(pat: str, owner: str, repo: str, branch: str, path: str,
              file_bytes: bytes, filename: str | None = None,
              text: str | None = None) -> bool:
    api = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    try:
        get = requests.get(api, headers=headers, timeout=30)
        if get.status_code == 200:
            return True
        if get.status_code == 404:
            event_type = _event_type(text or "")
            commit_message = f"Upload {event_type} file: {path}\n\n{text or ''}"
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


def write_design_json(owner: str, repo: str, branch: str, path: str,
                      content: dict) -> bool:
    pat = get_settings().github_pat
    if not pat:
        return False
    import json as _json
    json_bytes = _json.dumps(content, indent=2).encode("utf-8")
    return _put_file(pat, owner, repo, branch, path, json_bytes, filename=path.rsplit("/", 1)[-1],
                     text="[DESIGN UPLOAD EVENT]")


def append_order_to_design(owner: str, repo: str, branch: str, json_path: str,
                           order_entry: dict) -> bool:
    pat = get_settings().github_pat
    if not pat:
        return False
    import json as _json
    api = f"https://api.github.com/repos/{owner}/{repo}/contents/{json_path}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    try:
        get = requests.get(api, headers=headers, timeout=30)
        if get.status_code != 200:
            logger.warning("design json GET %s for %s/%s:%s", get.status_code, owner, repo, json_path)
            return False
        body = get.json()
        existing = _json.loads(base64.b64decode(body["content"]).decode("utf-8"))
        if "orders" not in existing:
            existing["orders"] = []
        existing["orders"].append(order_entry)
        json_bytes = _json.dumps(existing, indent=2).encode("utf-8")
        commit_message = f"Append order to design: {json_path}"
        put = requests.put(api, headers=headers, timeout=60, json={
            "message": commit_message,
            "content": base64.b64encode(json_bytes).decode("ascii"),
            "branch": branch,
            "sha": body["sha"],
        })
        return put.status_code in (200, 201)
    except requests.RequestException as exc:
        logger.warning("append_order failed: %s", exc)
        return False


def list_design_directory(owner: str, repo: str, path: str) -> list[dict] | None:
    pat = get_settings().github_pat
    if not pat:
        return None
    api = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    try:
        resp = requests.get(api, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("list_design_directory GET %s for %s/%s:%s", resp.status_code, owner, repo, path)
        return None
    except requests.RequestException as exc:
        logger.warning("list_design_directory failed: %s", exc)
        return None


def get_file_content(owner: str, repo: str, path: str) -> bytes | None:
    pat = get_settings().github_pat
    if not pat:
        return None
    api = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    try:
        resp = requests.get(api, headers=headers, timeout=30)
        if resp.status_code == 200:
            body = resp.json()
            return base64.b64decode(body["content"])
        return None
    except requests.RequestException as exc:
        logger.warning("get_file_content failed: %s", exc)
        return None
