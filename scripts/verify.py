#!/usr/bin/env python3
"""Verify repository signatures, index contents and the public file boundary."""

import hashlib
import json
from pathlib import Path
import sys

from fdroidserver import common, index

ROOT = Path(__file__).resolve().parents[1]


def verify(site):
    """Reject incomplete, unsigned or unexpected public repository artifacts."""
    config = json.loads((ROOT / "apps.json").read_text())
    state = json.loads((site / "state.json").read_text())
    fingerprint = (site / "fingerprint.txt").read_text().strip()
    common.config = common.default_config.copy()
    common.fill_config_defaults(common.config)
    signed_index, _, actual_fingerprint = index.get_index_from_jar(
        site / "fdroid/repo/index-v1.jar", fingerprint, allow_deprecated=True)
    if actual_fingerprint.replace(" ", "").upper() != fingerprint:
        raise ValueError("Repository signing certificate changed")
    entry, _, _ = index.get_index_from_jar(site / "fdroid/repo/entry.jar", fingerprint)
    v2_bytes = (site / "fdroid/repo/index-v2.json").read_bytes()
    if hashlib.sha256(v2_bytes).hexdigest() != entry["index"]["sha256"]:
        raise ValueError("Signed v2 index checksum mismatch")
    expected = {app["id"] for app in config["apps"]}
    if set(signed_index["packages"]) != expected:
        raise ValueError("Repository must contain exactly the configured apps")
    if set(json.loads(v2_bytes)["packages"]) != expected:
        raise ValueError("V2 repository must contain both apps")
    for app in config["apps"]:
        entry = state["apps"][app["id"]]
        packages = signed_index["packages"][app["id"]]
        if {p["versionCode"] for p in packages} != {p["version_code"] for p in entry["versions"]}:
            raise ValueError(f"Index version mismatch for {app['id']}")
        for package in packages:
            apk = site / "fdroid/repo" / package["apkName"]
            if hashlib.sha256(apk.read_bytes()).hexdigest() != package["hash"]:
                raise ValueError(f"Index APK checksum mismatch: {apk.name}")
    for path in site.rglob("*"):
        if path.is_file() and (path.suffix in {".keystore", ".jks", ".yml", ".pem"}
                               or "password" in path.name or path.name == "config.py"):
            raise ValueError(f"Private file in public output: {path}")
    for name in ("entry.jar", "index-v2.json", "index-v1.jar"):
        if not (site / "fdroid/repo" / name).is_file():
            raise ValueError(f"Missing F-Droid index: {name}")
    print("Verified signed repository: both apps, APK hashes, versions and public files")


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
