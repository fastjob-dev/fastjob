#!/usr/bin/env python3
"""
FastJob Release Script
Automates cleaning, formatting, building, and publishing to PyPI
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
from typing import List


class ReleaseManager:
    """Manages the release process for FastJob"""

    def __init__(self, dry_run: bool = False, test_pypi: bool = False):
        self.dry_run = dry_run
        self.test_pypi = test_pypi
        self.project_root = Path(__file__).parent

    def run_command(self, cmd: List[str], description: str) -> bool:
        """Run a shell command with error handling"""
        print(f"\n🔧 {description}")
        print(f"Running: {' '.join(cmd)}")

        if self.dry_run:
            print("  [DRY RUN] Command would run here")
            return True

        try:
            result = subprocess.run(
                cmd, cwd=self.project_root, check=True, capture_output=True, text=True
            )
            if result.stdout:
                print(result.stdout)
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error: {e}")
            if e.stderr:
                print(f"stderr: {e.stderr}")
            return False

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
            if not self.run_command(
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
            ):
                success = False

        # Files to remove
        clean_files = ["*.pyc", "*.pyo", ".coverage", "coverage.xml"]
        for pattern in clean_files:
            if not self.run_command(
                ["find", ".", "-name", pattern, "-type", "f", "-delete"],
                f"Removing {pattern} files",
            ):
                success = False

        return success

    def format_code(self) -> bool:
        """Format code using black and isort"""
        print("\n🎨 Formatting code...")

        # Check if formatters are available
        formatters = ["black", "isort"]
        for formatter in formatters:
            if not self.run_command(["which", formatter], f"Checking {formatter}"):
                print(f"⚠️ {formatter} not found. Install with: pip install {formatter}")
                return False

        # Format with black
        if not self.run_command(
            ["black", "fastjob/", "tests/", "examples/", "--line-length", "88"],
            "Formatting with black",
        ):
            return False

        # Sort imports with isort
        if not self.run_command(
            ["isort", "fastjob/", "tests/", "examples/", "--profile", "black"],
            "Sorting imports with isort",
        ):
            return False

        return True

    def lint_code(self) -> bool:
        """Run code quality checks"""
        print("\n🔍 Running code quality checks...")

        # Check if linters are available
        linters = ["flake8", "mypy"]
        available_linters = []

        for linter in linters:
            if self.run_command(["which", linter], f"Checking {linter}"):
                available_linters.append(linter)
            else:
                print(f"⚠️ {linter} not available, skipping...")

        # Run flake8 if available
        if "flake8" in available_linters:
            if not self.run_command(
                [
                    "flake8",
                    "fastjob/",
                    "--max-line-length",
                    "88",
                    "--ignore",
                    "E203,W503",
                ],
                "Running flake8 linter",
            ):
                print("⚠️ Flake8 found issues, but continuing...")

        # Run mypy if available
        if "mypy" in available_linters:
            if not self.run_command(
                ["mypy", "fastjob/", "--ignore-missing-imports"],
                "Running mypy type checker",
            ):
                print("⚠️ MyPy found issues, but continuing...")

        return True

    def run_tests(self) -> bool:
        """Run the test suite"""
        print("\n🧪 Running tests...")

        # Check if pytest is available
        if not self.run_command(["which", "pytest"], "Checking pytest"):
            print(
                "❌ pytest not found. Install with: pip install pytest pytest-asyncio"
            )
            return False

        # Run tests with coverage if available
        if self.run_command(["which", "coverage"], "Checking coverage"):
            return self.run_command(
                ["coverage", "run", "-m", "pytest", "tests/", "-v"],
                "Running tests with coverage",
            ) and self.run_command(["coverage", "report"], "Generating coverage report")
        else:
            return self.run_command(["pytest", "tests/", "-v"], "Running tests")

    def build_package(self) -> bool:
        """Build the distribution packages"""
        print("\n📦 Building distribution packages...")

        # Check if build tools are available
        if not self.run_command(["which", "python3"], "Checking Python"):
            return False

        # Install build if not available
        if not self.run_command(
            ["python3", "-c", "import build"], "Checking build module"
        ):
            print("Installing build module...")
            if not self.run_command(
                ["python3", "-m", "pip", "install", "build"], "Installing build module"
            ):
                return False

        # Build source and wheel distributions
        return self.run_command(
            ["python3", "-m", "build"], "Building source and wheel distributions"
        )

    def verify_package(self) -> bool:
        """Verify the built package"""
        print("\n✅ Verifying package...")

        # Check if twine is available
        if not self.run_command(["which", "twine"], "Checking twine"):
            print("Installing twine...")
            if not self.run_command(
                ["python3", "-m", "pip", "install", "twine"], "Installing twine"
            ):
                return False

        # Check the package
        return self.run_command(
            ["twine", "check", "dist/*"], "Checking package with twine"
        )

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

        return self.run_command(cmd, f"Uploading to {repo_name}")

    def run_release(
        self,
        skip_tests: bool = False,
        skip_format: bool = False,
        skip_build: bool = False,
        skip_publish: bool = False,
    ) -> bool:
        """Run the complete release process"""
        print("🚀 FastJob Release Process Starting...")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"Target: {'Test PyPI' if self.test_pypi else 'PyPI'}")

        steps = [
            ("clean", self.clean, True),
            ("format", self.format_code, not skip_format),
            ("lint", self.lint_code, not skip_format),
            ("test", self.run_tests, not skip_tests),
            ("build", self.build_package, not skip_build),
            ("verify", self.verify_package, not skip_build),
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
            print(f"FastJob has been published to {repo_name}!")

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
        "--clean-only", action="store_true", help="Only run the clean step"
    )

    args = parser.parse_args()

    # Change to the script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)

    release_manager = ReleaseManager(dry_run=args.dry_run, test_pypi=args.test_pypi)

    if args.clean_only:
        success = release_manager.clean()
    else:
        success = release_manager.run_release(
            skip_tests=args.skip_tests,
            skip_format=args.skip_format,
            skip_build=args.skip_build,
            skip_publish=args.skip_publish,
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
