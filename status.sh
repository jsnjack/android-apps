#!/bin/sh
# Compares each app's APK on the install page with the app's latest GitHub
# release, so a release that did not reach the page shows up.
set -eu
page=$(gh release view apps --repo jsnjack/android-apps --json assets -q '.assets[] | .name+" "+.label')
result=0
for entry in desklink:desklink.apk wallet:wallet.apk weather:weather-widget.apk wahoo-share:wahoo-share.apk; do
  repo=${entry%%:*}
  file=${entry#*:}
  on_page=$(printf '%s\n' "$page" | awk -v f="$file" '$1 == f {print $2}')
  latest=$(gh release view --repo "jsnjack/$repo" --json tagName -q .tagName 2>/dev/null | sed 's/^v//' || true)
  if [ -n "$on_page" ] && [ "$on_page" = "$latest" ]; then
    mark=ok
  else
    mark="differs: make release in $repo (make publish-apk retries the upload)"
    result=1
  fi
  printf '%-12s page %-8s latest release %-8s %s\n' "$repo" "${on_page:-none}" "${latest:-none}" "$mark"
done
exit $result
