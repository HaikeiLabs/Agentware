.PHONY: help evals evals-file-search evals-general evals-beta-tools evals-clean
.PHONY: python-lint python-typecheck python-test python-format
.PHONY: go-build go-test go-lint go-fmt go-vet

help:
	@echo "Available targets:"
	@echo "  python-lint        - Run ruff linter on Python code"
	@echo "  python-typecheck   - Run mypy type checker"
	@echo "  python-test        - Run pytest tests"
	@echo "  python-format      - Format Python code with ruff"
	@echo "  go-build           - Build Go module"
	@echo "  go-test            - Run Go tests"
	@echo "  go-lint            - Run golangci-lint"
	@echo "  go-fmt             - Format Go code"
	@echo "  go-vet             - Run Go vet"
	@echo ""
	@echo "  evals              - Run all evals (file search + general) sequentially against models"
	@echo "  evals-file-search  - Run only file search tool call evals"
	@echo "  evals-general      - Run only general tool calling evals"
	@echo "  evals-beta-tools   - Run only beta tool surface evals (python/src/evals)"
	@echo "  evals-clean        - Clean eval output files"
	@echo ""
	@echo "Environment variables / args:"
	@echo "  EVAL_BASE_URL      - API base URL (default: http://pedrogpt:8080/v1)"
	@echo "  EVAL_MODELS        - Comma-separated model list (default: gpt-oss,nemotron,qwen)"
	@echo "  --models           - Override models via CLI"
	@echo "  --base-url         - Override base URL via CLI"

python-lint:
	cd python && ruff check .

python-typecheck:
	cd python && mypy .

python-test:
	cd python && pytest

python-format:
	cd python && ruff format .

go-build:
	cd go && go build ./...

go-test:
	cd go && go test ./...

go-lint:
	cd go && golangci-lint run

go-fmt:
	cd go && gofmt -w .

go-vet:
	cd go && go vet ./...

evals:
	python3 -m testing.evals.main --all --models nemotron-3-super-120b

evals-file-search:
	python3 -m testing.evals.main --file-search --models nemotron-3-super-120b

evals-general:
	python3 -m testing.evals.main --general --models nemotron-3-super-120b

# Beta tool surface evals run against the maintained framework in
# python/src/evals (ruff + mypy clean), not the older testing/evals port.
# Authorization and tenancy are NOT evaluated here -- they are deterministic
# tests: cd python && pytest tests/beta_tool_authorization_test.py
# EVAL_BASE_URL / EVAL_MODELS / EVAL_BACKEND select the endpoint and model.
# An unreachable endpoint exits 2 with a BLOCKED message rather than
# recording a 0% score.
EVAL_BACKEND ?= llamacpp
evals-beta-tools:
	cd python && PYTHONPATH=src python3 -m evals.main --beta-tools \
		--backend $(EVAL_BACKEND)

evals-clean:
	rm -rf testing/evals/output/*.json
	rm -rf python/src/evals/output/*.json
	@echo "Cleaned eval output files"