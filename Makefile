.PHONY: all lint build

all: lint build

lint: mypy black flake8 isort

mypy:
	mypy \
		--disable-error-code "annotation-unchecked" \
		--follow-imports=silent \
		--ignore-missing-imports \
		--implicit-optional \
		-p vyper

black:
	black -C -t py311 vyper/ tests/ setup.py --force-exclude=vyper/version.py

flake8: black
	flake8 vyper/ tests/

isort: black
	isort vyper/ tests/ setup.py

build:
	pip install .

# run tests without forked tests (which require access to a node)
test:
	pytest tests/

coverage:
  COV_CORE_SOURCE=boa_zksync COV_CORE_CONFIG=.coveragerc COV_CORE_DATAFILE=.coverage.eager \
  pytest \
  --cov=boa_zksync \
  --cov-append \
  --cov-report term-missing:skip-covered \
  --cov-fail-under=70 \
  -nauto \
  tests

clean:
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +
	@find . -name '*~' -exec rm -f {} +
	@find . -name '__pycache__' -exec rmdir {} +

# note: for pypi upload, see pypi-publish.sh
