# Contributing to TradeMemory Protocol

Thanks for your interest in TradeMemory! 🎉

---

## Current Status

**This project is in early development (Phase 1).** We are not accepting external contributions yet while we build the core foundation.

However, you can still help:

### How to Help Right Now

1. **⭐ Star the repo** — Shows interest and helps us prioritize
2. **🐛 Report bugs** — If you find issues, open a GitHub Issue with:
   - What you expected to happen
   - What actually happened
   - Steps to reproduce
   - Your environment (OS, Python version, etc.)
3. **💬 Join the discussion** — Comment on open issues with your ideas
4. **📖 Improve documentation** — Found a typo or unclear explanation? Let us know via Issues

---

## When We'll Accept Contributions

**Phase 2 (planned for March 2026):** We'll open up contributions once the core architecture is stable. At that point we'll need help with:
- Additional broker integrations (Binance, Bybit, Alpaca)
- Advanced reflection algorithms
- Dashboard UI improvements
- Documentation translations
- Example trading strategies

We'll update this file when we're ready for external PRs.

---

## Development Setup (For Future Contributors)

Once we open contributions, here's how to set up your dev environment:

### Prerequisites
- Python 3.10+
- Git

### Setup Steps

```bash
# Fork and clone the repo
git clone https://github.com/YOUR_USERNAME/tradememory-protocol.git
cd tradememory-protocol

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install dev dependencies
pip install pytest black flake8

# Run tests to verify setup
pytest tests/

# Initialize database
python -m tradememory.db init
```

### Code Style

We use:
- **Black** for Python formatting
- **Flake8** for linting
- **Pytest** for testing

Run before committing:
```bash
black src/ tests/
flake8 src/ tests/
pytest tests/
```

---

## Pull Request Guidelines (When We Open)

When we start accepting PRs, we'll expect:

1. **One feature per PR** — Small, focused changes are easier to review
2. **Tests included** — New features need tests
3. **Documentation updated** — If you change behavior, update the docs
4. **No breaking changes** — Without discussion first
5. **Clean commit history** — Squash WIP commits before submitting

---

## Questions?

- **General questions:** Open a GitHub Discussion (coming soon)
- **Bug reports:** Open a GitHub Issue
- **Security issues:** Email security@sean.sys (do not open public issues)

---

## Code of Conduct

Be respectful. We're all here to build something useful.

- **DO:** Ask questions, propose ideas, point out bugs
- **DON'T:** Be rude, spam, or demand features

We reserve the right to block contributors who don't follow basic courtesy.

---

## License

By contributing to TradeMemory, you agree that your contributions will be licensed under the MIT License.

---

**Thanks for reading! We'll update this guide as the project matures. 🚀**
