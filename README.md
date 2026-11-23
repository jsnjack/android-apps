# android-apps (retired)

This repository published DeskLink, Wallet, Weather Widget and Wahoo Share to
a personal F-Droid repository through GitHub Actions. It was retired on
2026-11-23: each app is now published only as a signed APK on its own GitHub
release, built and signed locally by the app's `make release`.

Removed with it: the `publish.yml` workflow and its scripts, the GitHub Pages
site at https://jsnjack.github.io/android-apps/ (so the F-Droid repository URL
no longer answers), the Actions secrets, the `github-pages` environment, the
read-only deploy key on `jsnjack/wahoo-share`, and Actions for this
repository. The publisher's code is in the history before this commit.

The app signing key that all four apps use is `~/.android/debug.keystore`
(alias `androiddebugkey`, certificate SHA-256 `53d59ccc…13ebf`). The ignored
local `private/` folder holds the same key and the retired F-Droid index key;
keep its encrypted backup.
