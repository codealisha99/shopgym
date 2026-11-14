.PHONY: install test test-fast demo serve clean

install:
	uv sync
	uv run playwright install chromium

test:
	uv run pytest -q

test-fast:
	uv run pytest -q -m "not e2e"

demo:
	uv run shopgym demo

serve:
	uv run shopgym serve

clean:
	rm -rf data runs .coverage htmlcov
