#!/usr/bin/env python3
"""Configure the GitHub repository, scoped source access, secrets and Pages."""

import argparse
import base64
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def gh(*args, value=None):
    return subprocess.run(["gh", *args], input=value, text=True, check=True,
                          stdout=subprocess.PIPE).stdout


def configure():
    config = json.loads((ROOT / "apps.json").read_text())
    repository = config["repository"]
    private = ROOT / "private"
    for filename in ("app.keystore", "repo.keystore", "repo-password", "source-key", "source-key.pub"):
        if not (private / filename).is_file():
            raise ValueError(f"Missing local private file: {filename}")
    existing = subprocess.run(["gh", "repo", "view", repository, "--json", "name"],
                              text=True, capture_output=True)
    if existing.returncode:
        if "Could not resolve to a Repository" not in existing.stderr:
            raise RuntimeError(existing.stderr)
        gh("repo", "create", repository, "--public", "--description", config["description"])
    public_key = (private / "source-key.pub").read_text().strip()
    for app in config["apps"]:
        if not app["private"]:
            continue
        keys = json.loads(gh("api", f"repos/{app['source']}/keys"))
        if not any(key["key"] == " ".join(public_key.split()[:2]) for key in keys):
            gh("api", f"repos/{app['source']}/keys", "--method", "POST", "--input", "-",
               value=json.dumps({"title": f"{repository} read-only builds", "key": public_key, "read_only": True}))
    for name, filename, encode in [
        ("APP_KEYSTORE", "app.keystore", True),
        ("REPO_KEYSTORE", "repo.keystore", True),
        ("REPO_PASSWORD", "repo-password", False),
        ("SOURCE_SSH_KEY", "source-key", False),
    ]:
        data = (private / filename).read_bytes()
        value = base64.b64encode(data).decode() if encode else data.decode().strip() + "\n"
        gh("secret", "set", name, "--repo", repository, value=value)
        print(f"Configured {name}")
    print(f"Repository and secrets ready: https://github.com/{repository}")


def pages():
    repository = json.loads((ROOT / "apps.json").read_text())["repository"]
    result = subprocess.run(["gh", "api", f"repos/{repository}/pages"], text=True, capture_output=True)
    if result.returncode and "HTTP 404" not in result.stderr:
        raise RuntimeError(result.stderr)
    method = "POST" if result.returncode else "PUT"
    gh("api", f"repos/{repository}/pages", "--method", method, "--input", "-",
       value=json.dumps({"build_type": "workflow"}))
    print("GitHub Pages configured to deploy through Actions")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["configure", "pages"])
    args = parser.parse_args()
    {"configure": configure, "pages": pages}[args.action]()
