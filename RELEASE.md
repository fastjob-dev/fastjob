# FastJob Release Process

This document describes how to release FastJob to PyPI using the automated release script.

## Prerequisites

Install the required tools:

```bash
pip install build twine black isort flake8 mypy pytest pytest-asyncio coverage
```

## Release Script Usage

The `release.py` script automates the entire release process:

### Basic Usage

```bash
# Dry run to see what would happen
./release.py --dry-run

# Release to Test PyPI first (recommended)
./release.py --test-pypi

# Full release to PyPI
./release.py
```

### Advanced Options

```bash
# Skip specific steps
./release.py --skip-tests --skip-format
./release.py --skip-publish  # Build but don't publish

# Clean only
./release.py --clean-only
```

## Release Process Steps

The script performs these steps in order:

1. **Clean** - Remove build artifacts, cache files, old distributions
2. **Format** - Run `black` and `isort` to format code consistently  
3. **Lint** - Run `flake8` and `mypy` for code quality checks
4. **Test** - Run the full test suite with coverage
5. **Build** - Create source and wheel distributions
6. **Verify** - Check package integrity with `twine check`
7. **Publish** - Upload to PyPI (with confirmation prompt)

## Typical Release Workflow

### 1. Pre-release Testing

```bash
# Test the release process
./release.py --test-pypi --dry-run

# Actually publish to Test PyPI
./release.py --test-pypi
```

### 2. Production Release

```bash
# Final release to PyPI
./release.py
```

## Manual Steps (if needed)

If you need to run steps manually:

```bash
# Clean
find . -name "*.pyc" -delete
rm -rf build/ dist/ *.egg-info/

# Format
black fastjob/ tests/ examples/
isort fastjob/ tests/ examples/ --profile black

# Test
pytest tests/ -v

# Build
python -m build

# Verify
twine check dist/*

# Publish
twine upload dist/*                    # PyPI
twine upload --repository testpypi dist/*  # Test PyPI
```

## PyPI Credentials

Make sure you have PyPI credentials configured:

```bash
# Configure PyPI token
pip install keyring
keyring set https://upload.pypi.org/legacy/ __token__
# Enter your PyPI API token when prompted

# Or use .pypirc file
cat > ~/.pypirc << EOF
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-your-api-token-here

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-your-test-api-token-here
EOF
```

## Version Management

Before releasing, update the version in `pyproject.toml`:

```toml
[project]
name = "fastjob"
version = "0.2.0"  # Update this
```

## Troubleshooting

### Common Issues

**Build fails:**
- Check that all dependencies are installed
- Ensure tests pass locally
- Verify `pyproject.toml` is valid

**Upload fails:**
- Check PyPI credentials
- Ensure version number is not already used
- For first upload, ensure package name is available

**Tests fail:**
- Ensure test database exists: `createdb fastjob_test`
- Set environment variable: `export FASTJOB_DATABASE_URL="postgresql://postgres@localhost/fastjob_test"`

### Manual Debugging

```bash
# Run individual steps for debugging
./release.py --clean-only
./release.py --skip-tests --skip-publish  # Build only
./release.py --dry-run  # See what would run
```

## Security Notes

- Never commit PyPI tokens to git
- Use API tokens instead of passwords
- Test releases on Test PyPI first
- Verify package contents before publishing