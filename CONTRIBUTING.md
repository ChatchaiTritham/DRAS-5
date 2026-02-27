# Contributing to DRAS-5

Thank you for your interest in contributing to DRAS-5. This document provides guidelines for contributing to the project.

## Code of Conduct

Be respectful, inclusive, and constructive in all interactions.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/ChatchaiTritham/DRAS-5/issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs. actual behavior
   - System information (OS, Python version)
   - Code snippets if applicable

### Suggesting Enhancements

1. Check existing [Issues](https://github.com/ChatchaiTritham/DRAS-5/issues)
2. Create a new issue with:
   - Clear use case
   - Proposed solution
   - Potential impact on safety constraints (C1--C5)

### Pull Requests

1. Fork the repository
2. Create a new branch (`git checkout -b feature/your-feature-name`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`pytest tests/ -v`)
6. Update documentation if needed
7. Commit with clear messages
8. Push to your fork
9. Submit a pull request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR-USERNAME/DRAS-5.git
cd DRAS-5

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=dras5 --cov-report=html
```

## Coding Standards

### Python Style

- Follow PEP 8
- Use type hints
- Write docstrings (Google style)
- Maximum line length: 88 characters (Black default)

### Safety Constraints

Any code change must preserve the five safety invariants:

- **C1**: Monotonic escalation (no automatic state downgrades)
- **C2**: Timeout enforcement (bounded state duration)
- **C3**: Audit completeness (every transition logged)
- **C4**: Human approval gate (S4 -> S5 requires approval)
- **C5**: Controlled de-escalation (exponential decay + dual approval + single step)

### Testing

- Write unit tests for new functions
- Maintain test coverage
- Test edge cases and error conditions
- All 103+ existing tests must continue to pass

### Commit Messages

```
<type>: <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Example:

```
feat: Add configurable decay rate for C5 protocol

Allow lambda_k values to be specified at runtime while preserving
the default Table 2 parameters from the manuscript.

Closes #12
```

## Questions?

- Email: chatchait66@nu.ac.th
- Issues: https://github.com/ChatchaiTritham/DRAS-5/issues

Thank you for contributing!
