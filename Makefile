.PHONY: install conda-create validate test run dry-run force-send

install:
	python3 -m pip install -e '.[dev]'

conda-create:
	conda env create -f environment.yml

validate:
	paper-rec --root . validate --profile profiles/research.yaml

test:
	python3 -m pytest

run:
	paper-rec --root . run --profile profiles/research.yaml

dry-run:
	paper-rec --root . run --profile profiles/research.yaml --skip-send

force-send:
	paper-rec --root . run --profile profiles/research.yaml --force-send
