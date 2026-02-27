# Contributing to TRI-X

Thank you for your interest in contributing to TRI-X! This document provides guidelines for contributing to the project.

## Code of Conduct

Be respectful, inclusive, and constructive in all interactions.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/ChatchaiTritham/TRI-X/issues)
2. If not, create a new issue with:
 - Clear title and description
 - Steps to reproduce
 - Expected vs. actual behavior
 - System information (OS, Python version)
 - Code snippets if applicable

### Suggesting Enhancements

1. Check existing [Issues](https://github.com/ChatchaiTritham/TRI-X/issues) and [Discussions](https://github.com/ChatchaiTritham/TRI-X/discussions)
2. Create a new issue or discussion with:
 - Clear use case
 - Proposed solution
 - Potential impact

### Pull Requests

1. Fork the repository
2. Create a new branch (`git checkout -b feature/your-feature-name`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`pytest tests/`)
6. Update documentation if needed
7. Commit with clear messages
8. Push to your fork
9. Submit a pull request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR-USERNAME/TRI-X.git
cd TRI-X

# Create virtual environment
python -m venv venv
source venv/bin/activate # Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements.txt
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Check code style
black trix/ tests/
flake8 trix/ tests/
mypy trix/
```

## Coding Standards

### Python Style
- Follow PEP 8
- Use type hints
- Write docstrings (Google style)
- Maximum line length: 88 characters (Black default)

### Documentation
- Update README.md for user-facing changes
- Update docstrings for API changes
- Add examples for new features

### Testing
- Write unit tests for new functions
- Maintain >80% code coverage
- Test edge cases and error conditions

### Commit Messages
```
<type>: <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Example:
```
feat: Add LIME explainability method

Implement LIME (Local Interpretable Model-agnostic Explanations)
as an additional XAI method alongside SHAP and rule-based explanations.

Closes #42
```

## Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=trix --cov-report=html

# Run specific test
pytest tests/test_triage.py::test_risk_classification -v
```

## Documentation

```bash
# Build documentation
cd docs
make html

# View documentation
open _build/html/index.html
```

## Release Process

(For maintainers only)

1. Update version in `setup.py`
2. Update CHANGELOG.md
3. Create git tag: `git tag -a v1.0.0 -m "Release v1.0.0"`
4. Push tag: `git push origin v1.0.0`
5. GitHub Actions will build and publish to PyPI

## Questions?

- 📧 Email: chatchait66@nu.ac.th
- 💬 Discussions: https://github.com/ChatchaiTritham/TRI-X/discussions

Thank you for contributing! 🎉
