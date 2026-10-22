# Splendor Duel Engine - Development Commands
# Usage: make <target>

.PHONY: build-dev build-dev-debug test-rust test-all lint dev clean

# Build Rust extension in release mode and install to venv (fast, incremental)
build-dev:
	cargo build --release --manifest-path src/splendor_duel_engine/engine_rs/Cargo.toml
	maturin develop --no-build --manifest-path src/splendor_duel_engine/engine_rs/Cargo.toml

# Build Rust extension in debug mode and install to venv (faster compile, slower runtime)
build-dev-debug:
	cargo build --manifest-path src/splendor_duel_engine/engine_rs/Cargo.toml
	maturin develop --no-build --manifest-path src/splendor_duel_engine/engine_rs/Cargo.toml

# Run Rust parity tests
test-rust:
	uv run pytest tests/rust

# Run full test suite
test-all:
	uv run pytest

# Lint and format check
lint:
	uv run ruff check . && uv run ruff format . --check

# Default: build + run parity tests
dev: build-dev test-rust

# Full verification (build, test, lint)
verify: build-dev test-all lint

# Clean build artifacts
clean:
	cargo clean --manifest-path src/splendor_duel_engine/engine_rs/Cargo.toml
	rm -rf src/splendor_duel_engine/_core*.so src/splendor_duel_engine.egg-info

# Install in editable mode (full rebuild)
install-dev:
	uv run maturin develop --manifest-path src/splendor_duel_engine/engine_rs/Cargo.toml

# Show available targets
help:
	@echo "Available targets:"
	@echo "  build-dev        - Build release + install to venv (incremental)"
	@echo "  build-dev-debug  - Build debug + install to venv (incremental)"
	@echo "  test-rust        - Run Rust parity tests (the gate)"
	@echo "  test-all         - Run full test suite"
	@echo "  lint             - Run ruff check + format check"
	@echo "  dev              - Build + parity tests (default)"
	@echo "  verify           - Full verification (build + test + lint)"
	@echo "  install-dev      - Full rebuild + install (first time / after Cargo.lock change)"
	@echo "  clean            - Clean all build artifacts"
	@echo "  help             - Show this help"
