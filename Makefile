.PHONY: help evals evals-file-search evals-general evals-clean
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

evals-clean:
	rm -rf testing/evals/output/*.json
	@echo "Cleaned eval output files"