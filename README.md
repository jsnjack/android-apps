# Personal Android apps

One F-Droid repository for Wahoo Share and Weather Widget.

## Install

Install [F-Droid](https://f-droid.org/), add this repository in its repository
settings, refresh, then install either app:

**https://jsnjack.github.io/android-apps/fdroid/repo/**

The [install page](https://jsnjack.github.io/android-apps/) includes a QR code,
the repository fingerprint, and direct APK downloads. Requires Android 12+.
Allow F-Droid to install apps when Android asks. Update timing and unattended
installation depend on your client settings and Android version.

## Publishing

Run `make release` in either app repository after committing and pushing its
changes to `master`. Once its GitHub release upload succeeds, the command starts
this workflow for that app's exact source commit. It runs JVM tests, creates an
optimized release APK, signs it with the existing personal certificate, and
deploys the updated repository. The other app keeps its published APKs. Wahoo
source stays private; both APKs are publicly downloadable.

Retry a failed F-Droid trigger with `make fdroid-publish` in the app repository.
To trigger both apps manually from their current `master` branches:

```sh
gh workflow run publish.yml --repo jsnjack/android-apps
```

There is no scheduled polling. Builds use standard public GitHub runners.
The workflow runs serially, restores a
previous repository snapshot from GitHub Releases, retains three versions per
app, and deploys the complete signed site through GitHub Pages.

Source files are checked out from their existing repositories. This project
does not commit, change, or publish private source code. An existing app key is
required: a new runner-generated debug key cannot update your current apps.
App and repository signing are separate. Losing the repository key requires
adding a new repository; losing the app key prevents normal in-place updates.

Each changed app gets a `versionCode` above its previous published version.
App releases use the same version name and numeric version mapping as
`make release`; the publisher increases the code further if needed to avoid a downgrade.
After installing repository builds, local development APKs must use at least
that version code. Read it from the install page or `state.json`, then build:

```sh
APP_VERSION_CODE=3 APP_VERSION_NAME=dev ./gradlew \
  --init-script /path/to/android-apps/scripts/version.gradle :app:assembleDebug
```

Use the actual latest code for that app, not necessarily `3`. Matching signing
certificates preserve installed app data. A release build still needs a phone
smoke test, particularly for the widget and the Wahoo integration.

## Configuration and secrets

`apps.json` contains trusted source branches, package IDs, signing fingerprints,
descriptions and version baselines. `github-known-hosts` pins GitHub SSH host keys.

Repository Actions secrets:

| Secret | Value |
|---|---|
| `APP_KEYSTORE` | Base64 of the existing personal app keystore |
| `REPO_KEYSTORE` | Base64 of the separate repository keystore |
| `REPO_PASSWORD` | Repository keystore password |
| `SOURCE_SSH_KEY` | Private SSH key with read-only deploy access to Wahoo source |

The current personal app key uses alias `androiddebugkey` and password `android`.
No private files go into Git or the public site. Keep `private/` backed up in
encrypted storage. GitHub Pages must use **GitHub Actions** as its build source.

## Local validation

Install JDK 21, Android SDK platform 34 and build-tools 34.0.0, then:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
make check
export JAVA_HOME=/path/to/jdk-21
export ANDROID_HOME=/path/to/Android/Sdk
.venv/bin/python scripts/publish.py --local --sources /path/to/workspace
```

Local signing files are `private/app.keystore`, `private/app-password`,
`private/repo.keystore` and `private/repo-password`. Local validation snapshots
are marked and cannot be used as publication history. Normal runs clone trusted
remote source revisions; they never distribute uncommitted local changes.

The publisher verifies each APK's package, version, certificate and release
flag, then verifies the signed F-Droid index and all APK checksums. Failed
builds do not replace the deployed repository. Release snapshots are durable;
Pages artifacts use a short retention period.

Official references: [F-Droid repository setup](https://f-droid.org/en/docs/Setup_an_F-Droid_App_Repo/),
[Android signing](https://developer.android.com/studio/publish/app-signing),
[GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).
