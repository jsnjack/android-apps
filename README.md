# android-apps

The install page for my Android apps: https://jsnjack.github.io/android-apps/

Open it on the phone or tablet and tap **Install**. The page is `index.html`,
served by GitHub Pages straight from `main` (no build, no workflow). Its
buttons download the APKs attached to this repository's `apps` release:

| App | File |
|---|---|
| DeskLink | `desklink.apk` |
| Wallet | `wallet.apk` |
| Weather Widget | `weather-widget.apk` |
| Wahoo Share | `wahoo-share.apk` |

Each app's `make release` builds the signed release APK and replaces its file
here, with the version as the asset's label, which the page shows:

```sh
gh release upload apps bin/release/<file>#<version> --clobber --repo jsnjack/android-apps
```

`make status` here compares each app's file on the page with its latest
release and names the app whose release did not reach the page; `make
publish-apk` in that app's repository uploads it again.

Every app is signed with the personal key `~/.android/debug.keystore`
(alias `androiddebugkey`, certificate SHA-256 `53d59ccc…13ebf`), the key the
earlier F-Droid builds used, so a download installs over them. A new upload
must have a version code at least as high as the one it replaces.

The F-Droid repository, its GitHub Actions publisher and the snapshot
releases `repo-*` were retired on 2026-11-23; the publisher's code is in the
history. The ignored local `private/` folder keeps the signing key and the
retired F-Droid index key; keep its encrypted backup.
