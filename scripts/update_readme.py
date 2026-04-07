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

def update_readme(readme_path: str, new_content: str) -> bool:
    """
    Replace content between START_TAG and END_TAG in the README.
    Returns True if the file was modified, False otherwise.
    """
    if not os.path.exists(readme_path):
        print(f"Error: README not found at '{readme_path}'.")
        sys.exit(1)

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check that both tags exist
    if START_TAG not in content or END_TAG not in content:
        print(f"Error: Could not find update tags in {readme_path}.")
        print(f"  Make sure your README contains:")
        print(f"    {START_TAG}")
        print(f"    {END_TAG}")
        sys.exit(1)

    # Build the replacement block
    replacement = f"{START_TAG}\n{new_content}{END_TAG}"

    # Use regex to replace everything between (and including) the tags
    pattern = re.compile(
        re.escape(START_TAG) + r".*?" + re.escape(END_TAG),
        re.DOTALL,
    )
    new_readme = pattern.sub(replacement, content)

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

    markdown = build_markdown(repos)
    update_readme(args.readme, markdown)


if __name__ == "__main__":
    main()
