PYTHON := .venv/bin/python

check:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) -m compileall -q scripts tests
	$(PYTHON) -c "import yaml; yaml.safe_load(open('.github/workflows/publish.yml'))"

.PHONY: check
