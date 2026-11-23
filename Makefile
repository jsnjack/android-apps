# status compares each app's APK on the install page with its latest release.
status:
	@./status.sh

# icons converts the apps' launcher icons (from sibling checkouts) to icons/*.svg.
icons:
	python3 icons.py

.PHONY: status icons
