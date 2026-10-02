#!/usr/bin/env python3
"""Build trusted app revisions and assemble a signed, static F-Droid site."""

import argparse
import hashlib
import html
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("publisher")


def run(args, *, cwd=None, env=None, capture=False):
    """Run a checked command without expanding shell expressions."""
    LOG.debug("Running %s", args[0])
    return subprocess.run(args, cwd=cwd, env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def read_json(path):
    return json.loads(path.read_text())


def next_version(app, previous, release_version=None):
    """Allocate a version above both installed baselines and published versions."""
    code = max(app["version_floor"], previous.get("version_code", 0)) + 1
    if release_version:
        major, minor, patch = map(int, release_version.split("."))
        if minor >= 1000 or patch >= 1000:
            raise ValueError("Release minor and patch versions must be below 1000")
        code = max(code, major * 1000000 + minor * 1000 + patch)
    if code > 2100000000:
        raise ValueError("Android versionCode limit reached")
    return code


def verify_apk(path, app, code, tools):
    """Reject APKs with a wrong package, version, certificate or debug flag."""
    certs = run([str(tools / "apksigner"), "verify", "--print-certs", str(path)], capture=True)
    signers = re.findall(r"certificate SHA-256 digest: ([0-9a-f]+)", certs)
    if signers != [app["signer"]]:
        raise ValueError(f"Unexpected signing certificate for {app['id']}")
    badging = run([str(tools / "aapt"), "dump", "badging", str(path)], capture=True)
    package = re.search(r"package: name='([^']+)' versionCode='(\d+)'", badging)
    if not package or package.groups() != (app["id"], str(code)):
        raise ValueError(f"Wrong package/version for {path.name}")
    if "application-debuggable" in badging:
        raise ValueError(f"Refusing debuggable APK: {path.name}")


def source_revision(app, sources, local, requested_revision=None):
    """Read a trusted branch or the exact commit requested by an app release."""
    name = app["source"].split("/")[-1]
    checkout = sources / name
    if not local:
        remote = (f"git@github.com:{app['source']}.git" if app["private"]
                  else f"https://github.com/{app['source']}.git")
        if checkout.exists():
            actual_remote = run(["git", "remote", "get-url", "origin"], cwd=checkout, capture=True).strip()
            if actual_remote != remote or run(["git", "status", "--porcelain"], cwd=checkout, capture=True).strip():
                raise ValueError(f"Refusing to overwrite a modified source checkout: {checkout}")
            run(["git", "fetch", "--depth", "1", "origin", app["branch"]], cwd=checkout)
            run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=checkout)
        else:
            run(["git", "clone", "--depth", "1", "--branch", app["branch"],
                 remote, str(checkout)])
        if requested_revision:
            run(["git", "fetch", "--depth", "1", "origin", requested_revision], cwd=checkout)
            run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=checkout)
    revision = run(["git", "rev-parse", "HEAD"], cwd=checkout, capture=True).strip()
    if requested_revision and revision != requested_revision:
        raise ValueError(f"Source commit mismatch for {app['id']}")
    if local and run(["git", "status", "--porcelain"], cwd=checkout, capture=True).strip():
        revision += "-dirty"
    return checkout / app["directory"], revision


def publication_target(config, app, revision, release_version=None):
    """Validate release selection before accessing sources or signing files."""
    names = {item["source"].split("/")[-1] for item in config["apps"]}
    if app and app not in names:
        raise ValueError(f"Unknown app: {app}")
    if revision and (not app or not re.fullmatch(r"[0-9a-f]{40}", revision)):
        raise ValueError("An exact revision requires one app and a full lowercase commit SHA")
    if release_version and (not app or not re.fullmatch(r"\d+\.\d+\.\d+", release_version)):
        raise ValueError("A release version requires one app and a major.minor.patch version")


def preserved_app(app, old, previous, repo, tools, keep):
    """Keep an unselected app's published APKs without checking out its newer source."""
    if not old:
        raise ValueError(f"Publish all apps once before selecting only {app['id']}")
    versions = restore_versions(app, old, previous, repo, tools, keep)
    return dict(old, versions=versions)


def build_apk(project, app, revision, code, destination, tools, secrets, release_version=None):
    """Test, build and sign an optimized APK with the existing personal certificate."""
    version_name = release_version or f"{code}.{revision[:7]}"
    env = dict(os.environ, APP_VERSION_CODE=str(code), APP_VERSION_NAME=version_name)
    run([str(project / "gradlew"), "--no-daemon", "--init-script",
         str(ROOT / "scripts/version.gradle"), ":app:testDebugUnitTest", ":app:assembleRelease"],
        cwd=project, env=env)
    unsigned = project / "app/build/outputs/apk/release/app-release-unsigned.apk"
    run([str(tools / "apksigner"), "sign", "--ks", str(secrets / "app.keystore"),
         "--ks-key-alias", "androiddebugkey", "--ks-pass", "file:" + str(secrets / "app-password"),
         "--out", str(destination), str(unsigned)])
    verify_apk(destination, app, code, tools)
    return version_name


def restore_versions(app, old, previous, repo, tools, keep):
    """Restore verified historical APKs using a manifest, never an arbitrary directory copy."""
    versions = old.get("versions", [])[:keep]
    for version in versions:
        name = f"{app['id']}_{version['version_code']}.apk"
        if version["file"] != name:
            raise ValueError("Invalid filename in previous publication")
        source = previous / "fdroid/repo" / name
        if hashlib.sha256(source.read_bytes()).hexdigest() != version["sha256"]:
            raise ValueError(f"Stored APK checksum mismatch: {name}")
        verify_apk(source, app, version["version_code"], tools)
        shutil.copy2(source, repo / name)
    return versions


def write_metadata(app, entry, directory):
    metadata = {
        "Categories": ["Sports" if "wahoo" in app["id"] else "Weather"],
        "License": app["license"], "AuthorName": "Yauhen",
        "SourceCode": f"https://github.com/{app['source']}",
        "IssueTracker": f"https://github.com/{app['source']}/issues",
        "Name": app["name"], "Summary": app["summary"],
        "Description": app["description"], "AntiFeatures": ["NonFreeDep"],
        "CurrentVersion": entry["version_name"],
        "CurrentVersionCode": entry["version_code"],
    }
    (directory / f"{app['id']}.yml").write_text(yaml.safe_dump(metadata, sort_keys=False))


def repository_fingerprint(secrets):
    certificate = subprocess.run([
        "keytool", "-exportcert", "-keystore", str(secrets / "repo.keystore"),
        "-alias", "repository", "-storepass:file", str(secrets / "repo-password")],
        check=True, stdout=subprocess.PIPE).stdout
    return hashlib.sha256(certificate).hexdigest().upper()


def write_site(config, state, output, fingerprint):
    import qrcode
    url = config["url"] + "?fingerprint=" + fingerprint
    qrcode.make(url).save(output / "repository-qr.png")
    cards = []
    for app in config["apps"]:
        entry = state["apps"][app["id"]]
        href = "fdroid/repo/" + entry["versions"][0]["file"]
        cards.append(f'<article><h2>{html.escape(app["name"])}</h2>'
                     f'<p>{html.escape(app["summary"])}</p>'
                     f'<p>Version {html.escape(entry["version_name"])}</p>'
                     f'<a href="{html.escape(href)}">Download APK</a></article>')
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(config['name'])}</title>
<style>body{{font:18px system-ui;max-width:780px;margin:3rem auto;padding:0 1rem;line-height:1.6;background:#fafaf8;color:#182b2a}}a{{color:#086c61}}article{{padding:1rem 0;border-top:1px solid #ddd}}code{{overflow-wrap:anywhere;font-size:14px}}img{{width:220px;max-width:100%}}</style>
<h1>{html.escape(config['name'])}</h1><p>Install F-Droid, then add this repository to get these apps and their updates.</p>
<p><a href="{html.escape(url)}">Add repository to F-Droid</a> · <a href="https://f-droid.org/">Get F-Droid</a></p>
<p><code>{html.escape(config['url'])}</code></p>
<img src="repository-qr.png" alt="Scan to add the F-Droid repository">
<p>Repository fingerprint:<br><code>{fingerprint}</code></p>
{''.join(cards)}<p>Requires Android 12 or newer. Allow F-Droid to install apps when Android asks.</p>
<p>Weather Widget needs access to its configured weather server. Wahoo Share uses the Wahoo companion app.</p></html>'''
    (output / "index.html").write_text(page)
    (output / ".nojekyll").touch()
    (output / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    (output / "fingerprint.txt").write_text(fingerprint + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=ROOT / "work/sources")
    parser.add_argument("--local", action="store_true", help="Validate existing local checkouts; never publish dirty sources")
    parser.add_argument("--previous", type=Path, default=ROOT / "previous")
    parser.add_argument("--secrets", type=Path, default=ROOT / "private")
    parser.add_argument("--output", type=Path, default=ROOT / "public")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--app", help="Publish only wahoo-share or weather")
    parser.add_argument("--revision", help="Build this exact source commit for the selected app")
    parser.add_argument("--release-version", help="Use the app's major.minor.patch release version")
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(levelname)s: %(message)s")
    if args.trace:
        handler = logging.FileHandler("/tmp/android-apps.log", mode="w")
        handler.setLevel(logging.DEBUG)
        LOG.addHandler(handler)
        LOG.setLevel(logging.DEBUG)
    if os.environ.get("JAVA_HOME"):
        os.environ["PATH"] = str(Path(os.environ["JAVA_HOME"]) / "bin") + os.pathsep + os.environ["PATH"]
    config = read_json(ROOT / "apps.json")
    publication_target(config, args.app, args.revision, args.release_version)
    secrets = args.secrets.resolve()
    for filename in ("app.keystore", "app-password", "repo.keystore", "repo-password"):
        if not (secrets / filename).is_file():
            raise ValueError(f"Missing private signing file: {filename}")
    tools = Path(os.environ["ANDROID_HOME"]) / "build-tools/34.0.0"
    previous = args.previous.resolve()
    old_state = read_json(previous / "state.json") if (previous / "state.json").exists() else {"apps": {}}
    if old_state.get("validation_only"):
        raise ValueError("Cannot publish from a local validation snapshot")
    work = ROOT / "work/fdroid"
    if work.exists():
        shutil.rmtree(work)
    repo = work / "repo"
    metadata = work / "metadata"
    repo.mkdir(parents=True)
    metadata.mkdir()
    state = {"apps": {}, "validation_only": args.local}
    changed = False
    for app in config["apps"]:
        old = old_state["apps"].get(app["id"], {})
        if args.app and app["source"].split("/")[-1] != args.app:
            entry = preserved_app(app, old, previous, repo, tools, config["keep_versions"])
            state["apps"][app["id"]] = entry
            write_metadata(app, entry, metadata)
            continue
        project, revision = source_revision(app, args.sources.resolve(), args.local, args.revision)
        rebuild = (args.local or args.force or revision != old.get("revision")
                   or bool(args.release_version and args.release_version != old.get("version_name")))
        versions = restore_versions(app, old, previous, repo, tools,
                                    config["keep_versions"] - int(rebuild))
        if rebuild:
            changed = True
            code = next_version(app, old, args.release_version)
            destination = repo / f"{app['id']}_{code}.apk"
            LOG.info("Building %s at %s, version %s", app["name"], revision, code)
            name = build_apk(project, app, revision, code, destination, tools, secrets, args.release_version)
            versions.insert(0, {"version_code": code, "file": destination.name,
                                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
            entry = {"revision": revision, "version_code": code, "version_name": name, "versions": versions}
        else:
            entry = dict(old, versions=versions)
        state["apps"][app["id"]] = entry
        write_metadata(app, entry, metadata)
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"changed={str(changed).lower()}\n")
    if not changed:
        LOG.info("Both apps are already current; no deployment needed")
        return
    fdroid_config = {
        "repo_url": config["url"], "repo_name": config["name"],
        "repo_description": config["description"], "sdk_path": os.environ["ANDROID_HOME"],
        "keystore": str(secrets / "repo.keystore"), "repo_keyalias": "repository",
        "keystorepass": (secrets / "repo-password").read_text().strip(),
        "keypass": (secrets / "repo-password").read_text().strip(),
        "archive_older": 0, "make_current_version_link": False,
    }
    config_path = work / "config.yml"
    config_path.touch(mode=0o600)
    config_path.write_text(yaml.safe_dump(fdroid_config))
    run([str(Path(sys.executable).with_name("fdroid")), "update", "--pretty"], cwd=work)
    if args.output.exists():
        shutil.rmtree(args.output)
    args.output.mkdir(parents=True)
    shutil.copytree(repo, args.output / "fdroid/repo")
    fingerprint = repository_fingerprint(secrets)
    write_site(config, state, args.output, fingerprint)
    run([sys.executable, str(ROOT / "scripts/verify.py"), str(args.output)])
    archive = ROOT / "repository.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(args.output.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(args.output))
    LOG.info("Verified repository assembled in %s", args.output)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        LOG.error("Publishing failed: %s", error)
        sys.exit(1)
