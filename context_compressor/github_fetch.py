"""
Lightweight GitHub PR fetch -- not a connector, no OAuth, no stored
account. This hits GitHub's public REST API (`api.github.com`) and the
public raw-content CDN (`raw.githubusercontent.com`) directly, using
Python's standard library only, and hands the result to
`git_diff.compress_diff()` exactly as if you'd pasted the diff and
file contents in yourself.

What this does NOT do:
  - No "connect your GitHub account" flow, no OAuth, no stored token
    by default.
  - No repo browsing / PR picker -- you give it one PR reference and
    it fetches that PR only.

Scope and limits:
  - Works out of the box for any PUBLIC repo. Unauthenticated calls
    are capped by GitHub at 60 requests/hour per IP.
  - For a private repo, or to raise that rate limit to 5000/hour, set
    the GITHUB_TOKEN env var to a personal access token (read-only
    `public_repo` or `repo` scope). This is a manual env var the
    caller controls -- still not an OAuth "connect" flow.
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Dict, Optional, Tuple

API_ROOT = "https://api.github.com"

_PR_URL_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)")
_PR_SHORTHAND_RE = re.compile(r"^([^/\s]+)/([^/\s#]+)#(\d+)$")


def parse_pr_reference(ref: str) -> Tuple[str, str, int]:
    """
    Accepts either a full PR URL
    (https://github.com/owner/repo/pull/123, trailing slash or
    /files etc. ignored) or the shorthand owner/repo#123.
    Returns (owner, repo, pr_number).
    """
    ref = ref.strip()
    m = _PR_URL_RE.match(ref)
    if not m:
        m = _PR_SHORTHAND_RE.match(ref)
    if not m:
        raise ValueError(
            f"couldn't parse a GitHub PR reference from {ref!r} -- expected a URL like "
            "https://github.com/owner/repo/pull/123 or shorthand owner/repo#123"
        )
    owner, repo, number = m.group(1), m.group(2), int(m.group(3))
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    return owner, repo, number


def _request(url: str, accept: str, token: Optional[str]) -> bytes:
    headers = {"Accept": accept, "User-Agent": "context-compressor"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(
                f"GitHub returned 404 for {url} -- wrong PR number, or a private repo "
                "and no (or an invalid) GITHUB_TOKEN"
            )
        if e.code == 403:
            raise RuntimeError(
                f"GitHub returned 403 for {url} -- likely rate-limited (60/hour without "
                "a token); set GITHUB_TOKEN to raise the limit"
            )
        raise RuntimeError(f"GitHub request failed ({e.code}): {url}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"couldn't reach GitHub: {e.reason}")


def fetch_pr_diff_and_files(
    owner: str, repo: str, pr_number: int, token: Optional[str] = None,
) -> Tuple[str, Dict[str, str]]:
    """
    Fetch a PR's unified diff plus the new (post-change) content of
    every file it touches. Returns (diff_text, file_contents), ready
    to pass straight into `git_diff.compress_diff(diff_text=...,
    file_contents=...)`.

    Files that can't be fetched as text (binary, or removed in the
    PR) are simply left out of file_contents -- compress_diff already
    reports those under `files_skipped` rather than failing.
    """
    token = token or os.environ.get("GITHUB_TOKEN")
    pr_url = f"{API_ROOT}/repos/{owner}/{repo}/pulls/{pr_number}"

    diff_text = _request(pr_url, "application/vnd.github.v3.diff", token).decode("utf-8", errors="ignore")

    pr_meta = json.loads(_request(pr_url, "application/vnd.github+json", token))
    head_sha = pr_meta["head"]["sha"]

    files_meta = []
    page = 1
    while True:
        page_bytes = _request(f"{pr_url}/files?per_page=100&page={page}", "application/vnd.github+json", token)
        page_data = json.loads(page_bytes)
        if not page_data:
            break
        files_meta.extend(page_data)
        if len(page_data) < 100:
            break
        page += 1

    file_contents: Dict[str, str] = {}
    for f in files_meta:
        if f.get("status") == "removed":
            continue
        path = f["filename"]
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{head_sha}/{path}"
        try:
            file_contents[path] = _request(raw_url, "application/vnd.github.raw", token).decode(
                "utf-8", errors="ignore"
            )
        except RuntimeError:
            continue  # binary or otherwise unavailable -- compress_diff will list it as skipped

    return diff_text, file_contents
