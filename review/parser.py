"""Parse review markdown files (frontmatter + body) for the dashboard."""

import os
import re
import yaml

REVIEW_DIR = os.path.dirname(__file__)


def list_outline_files() -> list[str]:
    return sorted(
        [f for f in os.listdir(REVIEW_DIR) if f.endswith(".md")],
        reverse=True,
    )


def parse_outline(filename: str) -> dict:
    path = os.path.join(REVIEW_DIR, filename)
    with open(path) as f:
        raw = f.read()

    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not match:
        return {"filename": filename, "frontmatter": {}, "body": raw}

    frontmatter = yaml.safe_load(match.group(1)) or {}
    body = match.group(2)
    return {"filename": filename, "frontmatter": frontmatter, "body": body}


def list_all_outlines() -> list[dict]:
    return [parse_outline(f) for f in list_outline_files()]


def update_status(filename: str, new_status: str):
    path = os.path.join(REVIEW_DIR, filename)
    with open(path) as f:
        raw = f.read()

    updated = re.sub(
        r"^status:\s*\S+", f"status: {new_status}", raw, count=1, flags=re.MULTILINE
    )
    with open(path, "w") as f:
        f.write(updated)
