#!/usr/bin/env python3
"""Fetch trending GitHub repos and output compact JSON for Claude to analyse."""

import json
import sys
import urllib.request
import urllib.error
import base64
from datetime import datetime, timezone, timedelta

API_BASE = "https://api.github.com"
COUNT = 5


def fetch():
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    url = (
        f"{API_BASE}/search/repositories"
        f"?q=created:>={week_ago}+stars:>=10"
        f"&sort=stars&order=desc&per_page={COUNT}"
    )
    headers = {
        "Accept": "application/vnd.github.mercy-preview+json",
        "User-Agent": "github-profile-updater",
    }

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())

    results = []
    for repo in data.get("items", [])[:COUNT]:
        full_name = repo["full_name"]

        # Fetch README snippet
        readme_snippet = ""
        try:
            req2 = urllib.request.Request(
                f"{API_BASE}/repos/{full_name}/readme", headers=headers
            )
            with urllib.request.urlopen(req2) as resp2:
                rd = json.loads(resp2.read().decode())
                content = base64.b64decode(rd.get("content", "")).decode("utf-8", errors="ignore")
                # Keep first 300 chars of meaningful text
                lines = [l.strip() for l in content.split("\n")
                         if l.strip() and not l.strip().startswith(("#", "!", "[!", "<!--", "---", "[![", "<"))]
                readme_snippet = " ".join(lines)[:300]
        except Exception:
            pass

        results.append({
            "name": full_name,
            "url": repo["html_url"],
            "desc": repo.get("description") or "",
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "lang": repo.get("language") or "",
            "topics": repo.get("topics", [])[:5],
            "created": repo.get("created_at", "")[:10],
            "readme": readme_snippet,
        })

    print(json.dumps(results, separators=(",", ":")))


if __name__ == "__main__":
    fetch()
