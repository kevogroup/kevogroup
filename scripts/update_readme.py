#!/usr/bin/env python3
"""
GitHub Profile README Updater
Fetches your latest repositories and updates your profile README automatically.

Usage:
    python update_readme.py                          # Uses GITHUB_USERNAME env var
    python update_readme.py --username octocat       # Explicit username
    python update_readme.py --count 10               # Show top 10 repos (default: 5)
    python update_readme.py --readme path/to/README  # Custom README path
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

START_TAG = "<!-- LATEST-PROJECTS:START -->"
END_TAG = "<!-- LATEST-PROJECTS:END -->"
CONTRIB_START_TAG = "<!-- CONTRIBUTIONS:START -->"
CONTRIB_END_TAG = "<!-- CONTRIBUTIONS:END -->"
TRENDING_START_TAG = "<!-- TRENDING:START -->"
TRENDING_END_TAG = "<!-- TRENDING:END -->"
DEFAULT_COUNT = 5
MAX_COUNT = 10
API_BASE = "https://api.github.com"


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def build_headers():
    """Build request headers, including auth token if available."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-updater",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_repos(username: str, count: int) -> list[dict]:
    """
    Fetch public repositories for a user, sorted by most recently updated.
    Excludes forks and archived repos.
    """
    repos = []
    page = 1
    per_page = 100  # max allowed by GitHub API

    while len(repos) < count:
        url = (
            f"{API_BASE}/users/{username}/repos"
            f"?type=owner&sort=updated&direction=desc"
            f"&per_page={per_page}&page={page}"
        )
        req = urllib.request.Request(url, headers=build_headers())

        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"Error: User '{username}' not found on GitHub.")
                sys.exit(1)
            elif e.code == 403:
                print("Error: API rate limit exceeded. Set a GITHUB_TOKEN to increase limits.")
                sys.exit(1)
            else:
                print(f"Error: GitHub API returned {e.code}: {e.reason}")
                sys.exit(1)

        if not data:
            break  # no more pages

        for repo in data:
            # Skip forks and archived repos
            if repo.get("fork") or repo.get("archived"):
                continue
            repos.append(repo)
            if len(repos) >= count:
                break

        page += 1

    return repos[:count]


def fetch_contributions(username: str, count: int) -> list[dict]:
    """
    Fetch repositories the user has contributed to (via merged pull requests)
    that they don't own. Uses the GitHub Search API.
    """
    url = (
        f"{API_BASE}/search/issues"
        f"?q=author:{username}+type:pr+is:merged+-user:{username}"
        f"&sort=updated&order=desc&per_page={count * 3}"
    )
    req = urllib.request.Request(url, headers=build_headers())

    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Warning: Could not fetch contributions ({e.code}). Skipping.")
        return []

    # Deduplicate by repo — we only want one entry per repo
    seen_repos = set()
    contributions = []

    for item in data.get("items", []):
        repo_url = item.get("repository_url", "")
        if repo_url in seen_repos:
            continue
        seen_repos.add(repo_url)

        # Fetch repo details for language/stars
        req2 = urllib.request.Request(repo_url, headers=build_headers())
        try:
            with urllib.request.urlopen(req2) as resp:
                repo = json.loads(resp.read().decode())
        except urllib.error.HTTPError:
            continue

        contributions.append({
            "name": repo["full_name"],
            "html_url": repo["html_url"],
            "description": repo.get("description"),
            "stargazers_count": repo.get("stargazers_count", 0),
            "language": repo.get("language"),
            "pr_title": item.get("title", ""),
            "pr_url": item.get("html_url", ""),
            "updated_at": item.get("closed_at") or item.get("updated_at", ""),
        })

        if len(contributions) >= count:
            break

    return contributions


def build_contributions_markdown(contributions: list[dict]) -> str:
    """Build the markdown table for the contributions section."""
    if not contributions:
        return "_No contributions to external repositories found yet._\n"

    lines = [
        "| Repository | Contribution | Stars | Language | Date |",
        "|:-----------|:-------------|:-----:|:--------:|:----:|",
    ]

    for c in contributions:
        name = c["name"]
        url = c["html_url"]
        pr_title = (c.get("pr_title") or "Contribution").replace("|", "\\|")
        if len(pr_title) > 60:
            pr_title = pr_title[:57] + "..."
        pr_url = c.get("pr_url", "")
        stars = c.get("stargazers_count", 0)
        language = c.get("language")
        updated = c.get("updated_at", "")

        star_display = f":star: {stars}" if stars > 0 else "—"
        lang_display = format_language(language) if language else "—"
        date_display = format_date(updated) if updated else "—"

        pr_link = f"[{pr_title}]({pr_url})" if pr_url else pr_title

        lines.append(
            f"| [**{name}**]({url}) | {pr_link} | {star_display} | {lang_display} | {date_display} |"
        )

    lines.append("")
    lines.append(f"> Last updated: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}")
    lines.append("")

    return "\n".join(lines)


def fetch_trending(count: int) -> list[dict]:
    """
    Fetch the most-starred repos created in the last 7 days across all of GitHub.
    This surfaces the newest, hottest projects people are sharing.
    """
    from datetime import timedelta
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    url = (
        f"{API_BASE}/search/repositories"
        f"?q=created:>={week_ago}+stars:>=10"
        f"&sort=stars&order=desc&per_page={count}"
    )
    req = urllib.request.Request(url, headers=build_headers())

    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Warning: Could not fetch trending repos ({e.code}). Skipping.")
        return []

    return data.get("items", [])[:count]


def build_trending_markdown(repos: list[dict]) -> str:
    """Build the markdown table for trending repos across GitHub."""
    if not repos:
        return "_Could not fetch trending repos._\n"

    lines = [
        "| # | Repository | Description | Stars | Language | Created |",
        "|:-:|:-----------|:------------|:-----:|:--------:|:-------:|",
    ]

    for i, repo in enumerate(repos, 1):
        name = repo["full_name"]
        url = repo["html_url"]
        description = (repo.get("description") or "_No description_").replace("|", "\\|")
        stars = repo.get("stargazers_count", 0)
        language = repo.get("language")
        created = repo.get("created_at", "")

        if len(description) > 70:
            description = description[:67] + "..."

        star_display = f":star: {stars:,}" if stars > 0 else "—"
        lang_display = format_language(language) if language else "—"
        date_display = format_date(created) if created else "—"

        lines.append(
            f"| {i} | [**{name}**]({url}) | {description} | {star_display} | {lang_display} | {date_display} |"
        )

    lines.append("")
    lines.append(f"> Showing the most-starred new repos from the past 7 days · Last updated: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------

def format_language(language: str | None) -> str:
    """Return a language badge or empty string."""
    if not language:
        return ""
    # Map common languages to colored circles
    colors = {
        "Python": "3572A5", "JavaScript": "f1e05a", "TypeScript": "3178c6",
        "Java": "b07219", "C++": "f34b7d", "C": "555555", "C#": "178600",
        "Go": "00ADD8", "Rust": "dea584", "Ruby": "701516", "PHP": "4F5D95",
        "Swift": "F05138", "Kotlin": "A97BFF", "Dart": "00B4AB",
        "HTML": "e34c26", "CSS": "563d7c", "Shell": "89e051",
        "Vue": "41b883", "Scala": "c22d40", "R": "198CE7",
    }
    color = colors.get(language, "888888")
    return f"![{language}](https://img.shields.io/badge/-{language}-{color}?style=flat-square&logo={language.lower()}&logoColor=white)"


def format_stars(count: int) -> str:
    """Format star count with icon."""
    if count == 0:
        return ""
    return f" :star: {count}"


def format_date(iso_string: str) -> str:
    """Convert ISO date to a friendly 'Month Day, Year' format."""
    dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    return dt.strftime("%b %d, %Y")


def build_markdown(repos: list[dict]) -> str:
    """Build the markdown table for the latest projects section."""
    if not repos:
        return "_No public repositories found._\n"

    lines = [
        "| Repository | Description | Stars | Language | Updated |",
        "|:-----------|:------------|:-----:|:--------:|:-------:|",
    ]

    for repo in repos:
        name = repo["name"]
        url = repo["html_url"]
        description = (repo.get("description") or "_No description_").replace("|", "\\|")
        stars = repo.get("stargazers_count", 0)
        language = repo.get("language")
        updated = repo.get("updated_at", "")

        # Truncate long descriptions
        if len(description) > 80:
            description = description[:77] + "..."

        star_display = f":star: {stars}" if stars > 0 else "—"
        lang_display = format_language(language) if language else "—"
        date_display = format_date(updated) if updated else "—"

        lines.append(
            f"| [**{name}**]({url}) | {description} | {star_display} | {lang_display} | {date_display} |"
        )

    lines.append("")
    lines.append(f"> Last updated: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# README update logic
# ---------------------------------------------------------------------------

def update_section(content: str, start_tag: str, end_tag: str, new_content: str) -> str:
    """Replace content between start_tag and end_tag. Returns updated string."""
    if start_tag not in content or end_tag not in content:
        return content  # tags not present, skip

    replacement = f"{start_tag}\n{new_content}{end_tag}"
    pattern = re.compile(
        re.escape(start_tag) + r".*?" + re.escape(end_tag),
        re.DOTALL,
    )
    return pattern.sub(replacement, content)


def update_readme(readme_path: str, projects_md: str, contributions_md: str | None = None, trending_md: str | None = None) -> bool:
    """
    Replace content between tag pairs in the README.
    Returns True if the file was modified, False otherwise.
    """
    if not os.path.exists(readme_path):
        print(f"Error: README not found at '{readme_path}'.")
        sys.exit(1)

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    if START_TAG not in content or END_TAG not in content:
        print(f"Error: Could not find project tags in {readme_path}.")
        sys.exit(1)

    new_readme = update_section(content, START_TAG, END_TAG, projects_md)

    if contributions_md is not None:
        new_readme = update_section(new_readme, CONTRIB_START_TAG, CONTRIB_END_TAG, contributions_md)

    if trending_md is not None:
        new_readme = update_section(new_readme, TRENDING_START_TAG, TRENDING_END_TAG, trending_md)

    if new_readme == content:
        print("README is already up to date — no changes needed.")
        return False

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_readme)

    print("README updated successfully.")
    return True


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Update your GitHub profile README with your latest repositories."
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("GITHUB_USERNAME", ""),
        help="GitHub username (or set GITHUB_USERNAME env var)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=int(os.environ.get("REPO_COUNT", DEFAULT_COUNT)),
        help=f"Number of repos to display (default: {DEFAULT_COUNT}, max: {MAX_COUNT})",
    )
    parser.add_argument(
        "--readme",
        default=os.environ.get("README_PATH", "README.md"),
        help="Path to the README file (default: README.md)",
    )
    args = parser.parse_args()

    # Validate inputs
    if not args.username:
        print("Error: No username provided.")
        print("  Use --username <name> or set the GITHUB_USERNAME environment variable.")
        sys.exit(1)

    count = min(max(args.count, 1), MAX_COUNT)

    print(f"Fetching top {count} repos for @{args.username}...")
    repos = fetch_repos(args.username, count)
    print(f"Found {len(repos)} repositories.")

    print(f"Fetching recent contributions for @{args.username}...")
    contributions = fetch_contributions(args.username, count)
    print(f"Found {len(contributions)} contributed repositories.")

    print("Fetching trending repos across GitHub...")
    trending = fetch_trending(count)
    print(f"Found {len(trending)} trending repositories.")

    projects_md = build_markdown(repos)
    contributions_md = build_contributions_markdown(contributions)
    trending_md = build_trending_markdown(trending)
    update_readme(args.readme, projects_md, contributions_md, trending_md)


if __name__ == "__main__":
    main()
