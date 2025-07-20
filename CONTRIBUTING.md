# Contributing to FastJob

Thank you for your interest in contributing to FastJob! This document provides guidelines for contributing to the FastJob ecosystem.

## Project Structure

FastJob uses a tiered architecture:

- **fastjob** (Base Package): Core job processing functionality - MIT licensed
- **fastjob-pro**: Pro features (dashboard, recurring jobs, advanced scheduling) - Commercial license
- **fastjob-enterprise**: Enterprise features (metrics, logging, webhooks, dead letter management) - Commercial license

## How to Contribute

### Reporting Issues

1. **Search existing issues** first to avoid duplicates
2. **Use issue templates** when creating new issues
3. **Provide clear reproduction steps** for bugs
4. **Include system information** (Python version, OS, FastJob version)

### Suggesting Features

1. **Check the roadmap** in the README to see if your feature is already planned
2. **Open a discussion** first for major features to get feedback
3. **Consider which tier** the feature belongs to (Base/Pro/Enterprise)
4. **Provide use cases** and examples of how the feature would be used

### Contributing Code

#### Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/yourusername/fastjob.git
   cd fastjob
   ```

3. **Set up development environment**:
   ```bash
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install base package in development mode
   cd fastjob
   pip install -e ".[dev]"
   
   # Install additional packages if working on Pro/Enterprise features
   cd ../fastjob-pro
   pip install -e ".[dev,dashboard]"
   
   cd ../fastjob-enterprise  
   pip install -e ".[dev,all]"
   ```

4. **Set up database for testing**:
   ```bash
   # Create test database
   createdb fastjob_test
   export FASTJOB_DATABASE_URL="postgresql://user:password@localhost/fastjob_test"
   ```

#### Development Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the coding standards below

3. **Write tests** for your changes:
   ```bash
   # Run tests for specific package
   cd fastjob && python -m pytest tests/ -v
   cd fastjob-pro && python -m pytest tests/ -v
   cd fastjob-enterprise && python -m pytest tests/ -v
   ```

4. **Run the full test suite**:
   ```bash
   # From project root
   python verify_structure.py  # Verify package structure
   ```

5. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

6. **Push to your fork** and **create a pull request**

#### Coding Standards

- **Python Style**: Follow PEP 8 guidelines
- **Type Hints**: Use type hints for all function parameters and return values
- **Docstrings**: Use Google-style docstrings for all public functions and classes
- **Error Handling**: Provide clear, actionable error messages
- **Async/Await**: Use async/await consistently throughout the codebase
- **Testing**: Write comprehensive tests for all new functionality

#### Code Example

```python
import asyncio
from typing import Optional
from pydantic import BaseModel

class JobArgs(BaseModel):
    """Arguments for example job function."""
    user_id: int
    message: str
    priority: Optional[int] = 100

@fastjob.job(retries=3, args_model=JobArgs)
async def send_notification(user_id: int, message: str, priority: int = 100) -> None:
    """
    Send notification to user.
    
    Args:
        user_id: The ID of the user to notify
        message: The notification message
        priority: Message priority (lower = higher priority)
        
    Raises:
        NotificationError: If notification fails to send
    """
    try:
        # Implementation here
        await send_notification_impl(user_id, message, priority)
    except Exception as e:
        raise NotificationError(f"Failed to send notification to user {user_id}: {e}")
```

## Package-Specific Guidelines

### Base Package (fastjob)

- **Focus**: Core job processing functionality only
- **Dependencies**: Minimal - only essential dependencies (asyncpg, pydantic)
- **Compatibility**: Must work with all Python 3.10+ versions
- **Testing**: Comprehensive test coverage required

**Acceptable contributions:**
- Bug fixes in core functionality
- Performance improvements
- Security enhancements
- Documentation improvements
- Core CLI improvements

### Pro Package (fastjob-pro)

- **Focus**: Professional features that enhance developer productivity
- **Dependencies**: Can include web framework dependencies (FastAPI, uvicorn)
- **Features**: Dashboard, recurring jobs, advanced scheduling

**Contribution guidelines:**
- Must not break compatibility with base package
- Should enhance existing workflows, not replace them
- Pro features should be clearly documented with usage examples

### Enterprise Package (fastjob-enterprise)

- **Focus**: Production-grade features for enterprise deployments
- **Dependencies**: Can include enterprise-grade dependencies (structured logging, monitoring)
- **Features**: Metrics, webhooks, dead letter management, structured logging

**Contribution guidelines:**
- Must maintain backward compatibility
- Should focus on operational excellence and monitoring
- Enterprise features should be configurable and optional

## Testing Requirements

### Test Coverage

- **Minimum 90% test coverage** for all new code
- **Unit tests** for individual functions and classes
- **Integration tests** for database interactions
- **End-to-end tests** for complete workflows

### Test Structure

```python
import pytest
import asyncio
from fastjob import job, enqueue
from tests.conftest import setup_test_db

class TestJobProcessing:
    """Test job processing functionality."""
    
    @pytest.mark.asyncio
    async def test_job_enqueue_and_process(self, setup_test_db):
        """Test that jobs can be enqueued and processed successfully."""
        @job()
        async def test_job(message: str) -> str:
            return f"Processed: {message}"
        
        # Enqueue job
        job_id = await enqueue(test_job, message="Hello World")
        assert job_id is not None
        
        # Process job
        # ... rest of test
```

## Documentation

### Code Documentation

- **Docstrings**: All public functions, classes, and modules
- **Type hints**: Complete type annotations
- **Examples**: Include usage examples in docstrings

### User Documentation

- **README updates**: Update relevant README files for changes
- **API documentation**: Document any API changes
- **Migration guides**: Provide migration instructions for breaking changes

## Release Process

### Versioning

FastJob follows semantic versioning:
- **Major** (x.0.0): Breaking changes
- **Minor** (0.x.0): New features, backward compatible
- **Patch** (0.0.x): Bug fixes, backward compatible

### Release Checklist

1. Update version numbers in `pyproject.toml` files
2. Update CHANGELOG.md with release notes
3. Run full test suite across all packages
4. Update documentation
5. Create release notes with migration guidance

## Code of Conduct

### Be Respectful

- Use welcoming and inclusive language
- Respect different viewpoints and experiences
- Accept constructive criticism gracefully
- Focus on what's best for the community

### Be Collaborative

- Help newcomers get started
- Share knowledge and expertise
- Provide constructive feedback on pull requests
- Participate in discussions thoughtfully

## Getting Help

- **Documentation**: Check the README and development guide files
- **Issues**: Search existing issues for similar problems
- **Discussions**: Use GitHub Discussions for questions and ideas
- **Discord/Slack**: Join our community chat (links in README)

## Recognition

Contributors will be recognized in:
- CONTRIBUTORS.md file
- Release notes
- Documentation acknowledgments

## License

By contributing to FastJob, you agree that your contributions will be licensed under the same license as the project:
- **FastJob (base)**: MIT License
- **FastJob Pro/Enterprise**: Commercial License (contributions to commercial packages require a contributor agreement)

Thank you for contributing to FastJob! 🚀