# Contributing to TradeMemory Protocol

We welcome contributions! Whether it's bug fixes, new features, documentation improvements, or broker integrations — every contribution helps make AI trading agents smarter.

---

## Getting Started

### 1. Fork & Clone

```bash
# Fork the repo on GitHub, then:
git clone https://github.com/YOUR_USERNAME/tradememory-protocol.git
cd tradememory-protocol
```

### 2. Set Up Development Environment

```bash
python -m venv venv
source venv/bin/activate    # Linux/Mac
# venv\Scripts\activate     # Windows

pip install -e ".[dev]"
cp .env.example .env
```

### 3. Install Pre-commit Hooks

```bash
pre-commit install
```

This runs ruff, mypy, and formatting checks automatically on every commit.

### 4. Verify Setup

```bash
python -m pytest tests/ -v
# Expected: 67 passed
```

---

## Making Changes

### Branch Naming

Create a branch from `master` for your work:

```bash
git checkout -b feat/your-feature    # New feature
git checkout -b fix/your-bugfix      # Bug fix
git checkout -b docs/your-change     # Documentation
git checkout -b refactor/your-change # Refactoring
```

### Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add Binance exchange connector
fix: correct timezone handling in reflection engine
docs: update API reference for risk tools
refactor: simplify state persistence logic
test: add integration tests for trade journal
```

### Code Style

- **Python 3.10+** — Use modern syntax (type hints, f-strings)
- **Linting** — [Ruff](https://docs.astral.sh/ruff/) for linting and formatting
- **Type checking** — [mypy](https://mypy-lang.org/) with `--ignore-missing-imports`
- **Type hints** — Required for public function signatures

```bash
# Lint and auto-fix
ruff check src/ tests/ --fix

# Type check
mypy src/tradememory/ --ignore-missing-imports

# Run tests
python -m pytest tests/ -v

# Run tests with coverage
python -m pytest tests/ --cov=src/tradememory
```

If you installed pre-commit hooks (step 3 above), these checks run automatically on `git commit`.

### Testing Requirements

**All PRs must pass tests.** No exceptions.

- Add tests for new features in `tests/`
- Ensure existing tests still pass: `python -m pytest tests/ -v`
- Aim for meaningful test coverage, not 100% line coverage

---

## Submitting a Pull Request

### 1. Push Your Branch

```bash
git push origin feat/your-feature
```

### 2. Create the PR

- Open a PR against the `master` branch
- Use a clear title (e.g., "feat: add Binance connector")
- Fill in the PR template with:
  - **Summary** — What does this PR do?
  - **Test plan** — How did you verify it works?

### 3. PR Checklist

Before submitting, confirm:

- [ ] `python -m pytest tests/ -v` passes (67+ tests)
- [ ] New features include tests
- [ ] `ruff check` and `mypy` pass (or use pre-commit hooks)
- [ ] Commit messages follow conventional commits
- [ ] Documentation updated if behavior changed
- [ ] No secrets, API keys, or credentials in the code

### 4. Review Process

- A maintainer will review your PR
- Address any feedback with additional commits
- Once approved, we'll merge it

---

## What We're Looking For

### High Priority

- **Broker integrations** — Binance, Bybit, Alpaca, Interactive Brokers
- **Reflection algorithms** — Better pattern detection, multi-timeframe analysis
- **Performance optimizations** — Faster queries, better caching

### Also Welcome

- Documentation improvements and translations
- Dashboard UI enhancements
- Example trading strategies
- Bug reports and fixes
- Test coverage improvements

---

## Issue Guidelines

### Bug Reports

Use the [Bug Report template](https://github.com/mnemox-ai/tradememory-protocol/issues/new?template=bug_report.yml) and include:

- Steps to reproduce
- Expected vs actual behavior
- Environment (OS, Python version)
- Error messages or logs

### Feature Requests

Use the [Feature Request template](https://github.com/mnemox-ai/tradememory-protocol/issues/new?template=feature_request.yml) and include:

- Problem description
- Proposed solution
- Use case

---

## Architecture Notes

Before contributing, understand the key design principles:

1. **Platform-agnostic core** — TradeMemory does NOT connect to brokers directly. Broker-specific code stays in adapters (`trade_adapter.py`, `mt5_sync.py`).
2. **3-Layer Memory** — L1 (Hot/RAM), L2 (Warm/JSON), L3 (Cold/SQLite). Respect the layer boundaries.
3. **All timestamps in UTC** — No exceptions.
4. **LLM outputs are untrusted** — Always validate and provide fallback defaults.

See [Architecture Overview](docs/ARCHITECTURE.md) for the full design.

---

## Code of Conduct

Be respectful. We're all here to build something useful.

- **DO:** Ask questions, propose ideas, report bugs, share insights
- **DON'T:** Be rude, spam, or demand features

We reserve the right to block contributors who don't follow basic courtesy.

---

## License

By contributing to TradeMemory Protocol, you agree that your contributions will be licensed under the [MIT License](LICENSE).

---

**Thanks for contributing! Every PR makes AI trading agents a little smarter.**

Built by [Mnemox](https://mnemox.ai) — AI memory infrastructure.
