#!/usr/bin/env python3
"""
FastJob Release Script
Automates cleaning, formatting, building, and publishing to PyPI

Features:
- Automated version bumping
- Comprehensive testing and validation
- Support for Test PyPI and production PyPI
- Git tag creation and validation
- Pre-commit hook integration
- Dependency security checking
"""

import os
import sys
import subprocess
import argparse
import re
import json
from pathlib import Path
from typing import List, Optional, Tuple
import datetime


class ReleaseManager:
    """Manages the release process for FastJob"""

    def __init__(self, dry_run: bool = False, test_pypi: bool = False, version: Optional[str] = None):
        self.dry_run = dry_run
        self.test_pypi = test_pypi
        self.version = version
        self.project_root = Path(__file__).parent
        self.pyproject_path = self.project_root / "pyproject.toml"

    def run_command(self, cmd: List[str], description: str, capture_output: bool = True, check: bool = True) -> Tuple[bool, str]:
        """Run a shell command with error handling"""
        print(f"\n🔧 {description}")
        print(f"Running: {' '.join(cmd)}")

        if self.dry_run and check:
            print("  [DRY RUN] Command would run here")
            return True, ""

        try:
            result = subprocess.run(
                cmd, 
                cwd=self.project_root, 
                check=check, 
                capture_output=capture_output, 
                text=True
            )
            if result.stdout and capture_output:
                print(result.stdout)
            return True, result.stdout if capture_output else ""
        except subprocess.CalledProcessError as e:
            print(f"❌ Error: {e}")
            if e.stderr:
                print(f"stderr: {e.stderr}")
            return False, e.stderr if capture_output else ""
        except FileNotFoundError:
            print(f"❌ Command not found: {cmd[0]}")
            return False, f"Command not found: {cmd[0]}"

    def get_current_version(self) -> Optional[str]:
        """Get current version from pyproject.toml"""
        try:
            with open(self.pyproject_path, 'r') as f:
                content = f.read()
            
            version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if version_match:
                return version_match.group(1)
            return None
        except FileNotFoundError:
            print(f"❌ pyproject.toml not found at {self.pyproject_path}")
            return None

    def update_version(self, new_version: str) -> bool:
        """Update version in pyproject.toml"""
        if self.dry_run:
            print(f"  [DRY RUN] Would update version to {new_version}")
            return True

        try:
            with open(self.pyproject_path, 'r') as f:
                content = f.read()
            
            # Update version line
            updated_content = re.sub(
                r'version\s*=\s*["\'][^"\']+["\']',
                f'version = "{new_version}"',
                content
            )
            
            with open(self.pyproject_path, 'w') as f:
                f.write(updated_content)
            
            print(f"✅ Updated version to {new_version}")
            return True
        except Exception as e:
            print(f"❌ Failed to update version: {e}")
            return False

    def check_git_status(self) -> bool:
        """Check if git working directory is clean"""
        success, output = self.run_command(["git", "status", "--porcelain"], "Checking git status")
        if not success:
            return False
        
        if output.strip():
            print("❌ Git working directory is not clean. Please commit or stash changes.")
            print("Uncommitted changes:")
            print(output)
            return False
        
        print("✅ Git working directory is clean")
        return True

    def create_git_tag(self, version: str) -> bool:
        """Create and push git tag for the release"""
        tag_name = f"v{version}"
        
        # Check if tag already exists
        success, _ = self.run_command(["git", "tag", "-l", tag_name], f"Checking if tag {tag_name} exists")
        if success:
            _, output = self.run_command(["git", "tag", "-l", tag_name], "Getting tag list", check=False)
            if tag_name in output:
                print(f"❌ Tag {tag_name} already exists")
                return False

        # Create tag
        commit_msg = f"Release v{version}"
        success, _ = self.run_command(
            ["git", "tag", "-a", tag_name, "-m", commit_msg], 
            f"Creating tag {tag_name}"
        )
        if not success:
            return False

        # Push tag
        success, _ = self.run_command(["git", "push", "origin", tag_name], f"Pushing tag {tag_name}")
        return success

    def check_dependencies(self) -> bool:
        """Check for dependency vulnerabilities"""
        print("\n🔒 Checking dependencies for security vulnerabilities...")
        
        # Check if safety is available
        success, _ = self.run_command(["which", "safety"], "Checking safety tool", check=False)
        if not success:
            print("⚠️ Safety not installed. Install with: pip install safety")
            print("⚠️ Skipping security check...")
            return True
        
        # Run safety check
        success, _ = self.run_command(["safety", "check"], "Running safety check on dependencies")
        if not success:
            print("⚠️ Security vulnerabilities found, but continuing...")
        
        return True

    def clean(self) -> bool:
        """Clean build artifacts and cache files"""
        print("\n🧹 Cleaning build artifacts...")

        # Directories to remove
        clean_dirs = [
            "build",
            "dist", 
            "*.egg-info",
            "__pycache__",
            ".pytest_cache",
            ".coverage",
            "htmlcov",
        ]

        success = True
        for pattern in clean_dirs:
            result, _ = self.run_command(
                [
                    "find",
                    ".",
                    "-name",
                    pattern,
                    "-type",
                    "d",
                    "-exec",
                    "rm",
                    "-rf",
                    "{}",
                    "+",
                ],
                f"Removing {pattern} directories",
                check=False
            )
            if not result:
                success = False

        # Files to remove
        clean_files = ["*.pyc", "*.pyo", ".coverage", "coverage.xml"]
        for pattern in clean_files:
            result, _ = self.run_command(
                ["find", ".", "-name", pattern, "-type", "f", "-delete"],
                f"Removing {pattern} files",
                check=False
            )
            if not result:
                success = False

        return success

    def format_code(self) -> bool:
        """Format code using black and isort"""
        print("\n🎨 Formatting code...")

        # Check if formatters are available
        formatters = ["black", "isort"]
        for formatter in formatters:
            success, _ = self.run_command(["which", formatter], f"Checking {formatter}", check=False)
            if not success:
                print(f"⚠️ {formatter} not found. Install with: pip install {formatter}")
                return False

        # Format with black
        success, _ = self.run_command(
            ["black", "fastjob/", "tests/", "examples/", "--line-length", "88"],
            "Formatting with black",
        )
        if not success:
            return False

        # Sort imports with isort
        success, _ = self.run_command(
            ["isort", "fastjob/", "tests/", "examples/", "--profile", "black"],
            "Sorting imports with isort",
        )
        if not success:
            return False

        return True

    def lint_code(self) -> bool:
        """Run code quality checks"""
        print("\n🔍 Running code quality checks...")

        # Check if linters are available
        linters = ["flake8", "mypy"]
        available_linters = []

        for linter in linters:
            success, _ = self.run_command(["which", linter], f"Checking {linter}", check=False)
            if success:
                available_linters.append(linter)
            else:
                print(f"⚠️ {linter} not available, skipping...")

        # Run flake8 if available
        if "flake8" in available_linters:
            success, _ = self.run_command(
                [
                    "flake8",
                    "fastjob/",
                    "--max-line-length",
                    "88",
                    "--ignore",
                    "E203,W503",
                ],
                "Running flake8 linter",
                check=False
            )
            if not success:
                print("⚠️ Flake8 found issues, but continuing...")

        # Run mypy if available
        if "mypy" in available_linters:
            success, _ = self.run_command(
                ["mypy", "fastjob/", "--ignore-missing-imports"],
                "Running mypy type checker",
                check=False
            )
            if not success:
                print("⚠️ MyPy found issues, but continuing...")

        return True

    def run_tests(self) -> bool:
        """Run the test suite"""
        print("\n🧪 Running tests...")

        # Use FastJob's comprehensive test runner
        success, _ = self.run_command(["python3", "run_tests.py"], "Running FastJob test suite")
        return success

    def build_package(self) -> bool:
        """Build the distribution packages"""
        print("\n📦 Building distribution packages...")

        # Check if build tools are available
        success, _ = self.run_command(["which", "python3"], "Checking Python", check=False)
        if not success:
            return False

        # Install build if not available
        success, _ = self.run_command(
            ["python3", "-c", "import build"], "Checking build module", check=False
        )
        if not success:
            print("Installing build module...")
            success, _ = self.run_command(
                ["python3", "-m", "pip", "install", "build"], "Installing build module"
            )
            if not success:
                return False

        # Build source and wheel distributions
        success, _ = self.run_command(
            ["python3", "-m", "build"], "Building source and wheel distributions"
        )
        return success

    def verify_package(self) -> bool:
        """Verify the built package"""
        print("\n✅ Verifying package...")

        # Check if twine is available
        success, _ = self.run_command(["which", "twine"], "Checking twine", check=False)
        if not success:
            print("Installing twine...")
            success, _ = self.run_command(
                ["python3", "-m", "pip", "install", "twine"], "Installing twine"
            )
            if not success:
                return False

        # Check the package
        success, _ = self.run_command(
            ["twine", "check", "dist/*"], "Checking package with twine"
        )
        return success

    def publish_package(self) -> bool:
        """Publish package to PyPI"""
        print(f"\n🚀 Publishing to {'Test ' if self.test_pypi else ''}PyPI...")

        if self.dry_run:
            print("  [DRY RUN] Would publish to PyPI here")
            return True

        # Confirm publication
        repo_name = "Test PyPI" if self.test_pypi else "PyPI"
        confirm = input(f"Are you sure you want to publish to {repo_name}? (yes/no): ")
        if confirm.lower() != "yes":
            print("Publication cancelled.")
            return False

        # Upload to PyPI
        cmd = ["twine", "upload"]
        if self.test_pypi:
            cmd.extend(["--repository", "testpypi"])
        cmd.append("dist/*")

        success, _ = self.run_command(cmd, f"Uploading to {repo_name}")
        return success

    def run_release(
        self,
        skip_tests: bool = False,
        skip_format: bool = False,
        skip_build: bool = False,
        skip_publish: bool = False,
        skip_git_checks: bool = False,
    ) -> bool:
        """Run the complete release process"""
        print("🚀 FastJob Release Process Starting...")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"Target: {'Test PyPI' if self.test_pypi else 'PyPI'}")
        
        # Get current version
        current_version = self.get_current_version()
        if not current_version:
            print("❌ Could not determine current version")
            return False
        
        release_version = self.version if self.version else current_version
        print(f"Release version: {release_version}")

        steps = [
            ("git_status", self.check_git_status, not skip_git_checks and not self.dry_run),
            ("dependencies", self.check_dependencies, True),
            ("clean", self.clean, True),
            ("version_update", lambda: self.update_version(release_version) if self.version else True, bool(self.version)),
            ("format", self.format_code, not skip_format),
            ("lint", self.lint_code, not skip_format),
            ("test", self.run_tests, not skip_tests),
            ("build", self.build_package, not skip_build),
            ("verify", self.verify_package, not skip_build),
            ("git_tag", lambda: self.create_git_tag(release_version), not skip_git_checks and not skip_publish),
            ("publish", self.publish_package, not skip_publish),
        ]

        for step_name, step_func, should_run in steps:
            if not should_run:
                print(f"\n⏭️ Skipping {step_name}")
                continue

            if not step_func():
                print(f"\n❌ Release failed at step: {step_name}")
                return False

        print("\n🎉 Release process completed successfully!")
        if not self.dry_run and not skip_publish:
            repo_name = "Test PyPI" if self.test_pypi else "PyPI"
            print(f"FastJob v{release_version} has been published to {repo_name}!")
            
        return True


def main():
    parser = argparse.ArgumentParser(description="FastJob Release Manager")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually doing it",
    )
    parser.add_argument(
        "--test-pypi", action="store_true", help="Publish to Test PyPI instead of PyPI"
    )
    parser.add_argument(
        "--version", 
        help="Specify version to release (updates pyproject.toml)"
    )
    parser.add_argument("--skip-tests", action="store_true", help="Skip running tests")
    parser.add_argument(
        "--skip-format", action="store_true", help="Skip code formatting and linting"
    )
    parser.add_argument(
        "--skip-build", action="store_true", help="Skip building the package"
    )
    parser.add_argument(
        "--skip-publish", action="store_true", help="Skip publishing to PyPI"
    )
    parser.add_argument(
        "--skip-git-checks", action="store_true", help="Skip git status checks and tagging"
    )
    parser.add_argument(
        "--clean-only", action="store_true", help="Only run the clean step"
    )

    args = parser.parse_args()

    # Change to the script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)

    release_manager = ReleaseManager(
        dry_run=args.dry_run, 
        test_pypi=args.test_pypi,
        version=args.version
    )

    if args.clean_only:
        success = release_manager.clean()
    else:
        success = release_manager.run_release(
            skip_tests=args.skip_tests,
            skip_format=args.skip_format,
            skip_build=args.skip_build,
            skip_publish=args.skip_publish,
            skip_git_checks=args.skip_git_checks,
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
