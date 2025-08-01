"""
FastJob Exception Classes
Provides clear, actionable error messages for better debugging and monitoring.
"""

import re
from typing import Any, Dict, List, Optional


class FastJobError(Exception):
    """
    Base exception class for all FastJob errors.

    Provides structured error information and actionable guidance.
    """

    def __init__(
        self,
        message: str,
        error_code: str,
        context: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[str]] = None,
        documentation_url: Optional[str] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        self.suggestions = suggestions or []
        self.documentation_url = documentation_url

        # Create detailed error message
        super().__init__(self._format_error_message())

    def _format_error_message(self) -> str:
        """Format a comprehensive error message."""
        lines = [f"FastJob Error [{self.error_code}]: {self.message}"]

        if self.context:
            lines.append("\nContext:")
            for key, value in self.context.items():
                lines.append(f"  {key}: {value}")

        if self.suggestions:
            lines.append("\nSuggestions:")
            for suggestion in self.suggestions:
                lines.append(f"  • {suggestion}")

        if self.documentation_url:
            lines.append(f"\nDocumentation: {self.documentation_url}")

        return "\n".join(lines)


class DatabaseConnectionError(FastJobError):
    """Raised when database connection fails."""

    def __init__(self, original_error: Exception, database_url: Optional[str] = None):
        context = {
            "original_error": str(original_error),
            "error_type": type(original_error).__name__,
        }

        if database_url:
            # Mask password in URL for security
            masked_url = self._mask_database_url(database_url)
            context["database_url"] = masked_url

        suggestions = [
            "Verify that PostgreSQL is running and accessible",
            "Check database_url configuration is set correctly",
            "Ensure database exists and user has proper permissions",
            "Verify network connectivity to database server",
            "Check if firewall is blocking database port (default: 5432)",
        ]

        super().__init__(
            message="Failed to connect to PostgreSQL database",
            error_code="DB_CONNECTION_FAILED",
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.fastjob.dev/troubleshooting/database",
        )

    @staticmethod
    def _mask_database_url(url: str) -> str:
        """Mask password in database URL for security."""
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


class JobNotFoundError(FastJobError):
    """Raised when a job function is not found."""

    def __init__(self, job_name: str, available_jobs: Optional[List[str]] = None):
        context = {"job_name": job_name, "available_jobs": available_jobs or []}

        suggestions = [
            f"Ensure job function '{job_name}' is decorated with @fastjob.job()",
            "Check that the module containing the job is imported",
            "Verify job function name spelling and module path",
            "Run job discovery: fastjob.discover_jobs()",
            "Check FASTJOB_JOBS_MODULE environment variable if using auto-discovery",
        ]

        if available_jobs:
            suggestions.append(f"Available jobs: {', '.join(available_jobs)}")

        super().__init__(
            message=f"Job function '{job_name}' not found in job registry",
            error_code="JOB_NOT_FOUND",
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.fastjob.dev/guide/job-definition",
        )


class JobValidationError(FastJobError):
    """Raised when job arguments fail validation."""

    def __init__(
        self, job_name: str, validation_errors: List[str], provided_args: Dict[str, Any]
    ):
        context = {
            "job_name": job_name,
            "validation_errors": validation_errors,
            "provided_args": list(provided_args.keys()),
            "provided_values": {
                k: str(v)[:100] for k, v in provided_args.items()
            },  # Truncate long values
        }

        suggestions = [
            "Check job function signature and required arguments",
            "Ensure all required arguments are provided",
            "Verify argument types match expected types",
            "Check Pydantic model validation if using args_model",
            "Review job function documentation for expected parameters",
        ]

        error_details = "; ".join(validation_errors)

        super().__init__(
            message=f"Job '{job_name}' argument validation failed: {error_details}",
            error_code="JOB_VALIDATION_FAILED",
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.fastjob.dev/guide/type-validation",
        )


class JobExecutionError(FastJobError):
    """Raised when a job fails during execution."""

    def __init__(
        self,
        job_name: str,
        job_id: str,
        original_error: Exception,
        attempt: int,
        max_attempts: int,
        args: Optional[Dict[str, Any]] = None,
    ):
        context = {
            "job_name": job_name,
            "job_id": job_id,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "original_error": str(original_error),
            "error_type": type(original_error).__name__,
        }

        if args:
            context["job_args"] = {k: str(v)[:50] for k, v in args.items()}

        suggestions = [
            "Check job function implementation for errors",
            "Review job logs for detailed error information",
            "Verify job arguments are correct and complete",
            "Check if external dependencies (APIs, files) are available",
            "Consider increasing retry attempts if appropriate",
        ]

        if attempt < max_attempts:
            suggestions.append(
                f"Job will be retried (attempt {attempt + 1}/{max_attempts})"
            )
        else:
            suggestions.append(
                "Job will be moved to dead letter queue after max retries"
            )

        super().__init__(
            message=f"Job '{job_name}' failed on attempt {attempt}/{max_attempts}: {str(original_error)}",
            error_code="JOB_EXECUTION_FAILED",
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.fastjob.dev/troubleshooting/job-failures",
        )


class QueueError(FastJobError):
    """Raised when queue operations fail."""

    def __init__(
        self,
        operation: str,
        queue_name: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        context = {"operation": operation, "queue_name": queue_name, "reason": reason}

        if details:
            context.update(details)

        suggestions = [
            "Verify queue name is correct and exists",
            "Check database connectivity",
            "Ensure proper permissions for queue operations",
            "Check if queue is not full or blocked",
            "Review queue configuration settings",
        ]

        super().__init__(
            message=f"Queue operation '{operation}' failed for queue '{queue_name}': {reason}",
            error_code="QUEUE_OPERATION_FAILED",
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.fastjob.dev/guide/queues",
        )


class WorkerError(FastJobError):
    """Raised when worker operations fail."""

    def __init__(
        self,
        operation: str,
        reason: str,
        worker_config: Optional[Dict[str, Any]] = None,
    ):
        context = {"operation": operation, "reason": reason}

        if worker_config:
            context["worker_config"] = worker_config

        suggestions = [
            "Check worker configuration settings",
            "Verify database connection is stable",
            "Ensure sufficient system resources (CPU, memory)",
            "Check for conflicting processes or port usage",
            "Review worker logs for additional information",
        ]

        super().__init__(
            message=f"Worker operation '{operation}' failed: {reason}",
            error_code="WORKER_OPERATION_FAILED",
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.fastjob.dev/guide/workers",
        )


class ConfigurationError(FastJobError):
    """Raised when configuration is invalid or missing."""

    def __init__(
        self, setting: str, value: Any, reason: str, expected: Optional[str] = None
    ):
        context = {
            "setting": setting,
            "provided_value": str(value) if value is not None else "None",
            "reason": reason,
        }

        if expected:
            context["expected"] = expected

        suggestions = [
            f"Check {setting} configuration value",
            "Verify environment variables are set correctly",
            "Review configuration file syntax",
            "Check for typos in configuration keys",
            "Ensure configuration values are of correct type",
        ]

        if expected:
            suggestions.append(f"Expected format: {expected}")

        super().__init__(
            message=f"Configuration error for '{setting}': {reason}",
            error_code="CONFIGURATION_ERROR",
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.fastjob.dev/guide/configuration",
        )


class SchedulingError(FastJobError):
    """Raised when job scheduling fails."""

    def __init__(self, job_name: str, schedule_time: str, reason: str):
        context = {
            "job_name": job_name,
            "schedule_time": schedule_time,
            "reason": reason,
        }

        suggestions = [
            "Check schedule time format is correct",
            "Ensure schedule time is in the future",
            "Verify timezone settings if applicable",
            "Check cron expression syntax if using cron scheduling",
            "Review job scheduling documentation for valid formats",
        ]

        super().__init__(
            message=f"Failed to schedule job '{job_name}' for '{schedule_time}': {reason}",
            error_code="SCHEDULING_FAILED",
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.fastjob.dev/guide/scheduling",
        )


class MigrationError(FastJobError):
    """Raised when database migration fails."""

    def __init__(
        self,
        migration_step: str,
        reason: str,
        database_info: Optional[Dict[str, Any]] = None,
    ):
        context = {"migration_step": migration_step, "reason": reason}

        if database_info:
            context.update(database_info)

        suggestions = [
            "Check database connectivity and permissions",
            "Verify database user has DDL privileges",
            "Ensure no other processes are modifying the database",
            "Check available disk space on database server",
            "Review migration logs for detailed error information",
        ]

        super().__init__(
            message=f"Database migration failed at step '{migration_step}': {reason}",
            error_code="MIGRATION_FAILED",
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.fastjob.dev/guide/migrations",
        )


def create_user_friendly_error(
    error: Exception, context: Optional[Dict[str, Any]] = None
) -> FastJobError:
    """
    Convert generic exceptions to user-friendly FastJob errors.

    Args:
        error: Original exception
        context: Additional context information

    Returns:
        FastJobError: User-friendly error with actionable suggestions
    """
    if isinstance(error, FastJobError):
        return error

    error_type = type(error).__name__
    error_message = str(error)

    # Map common errors to specific FastJob errors
    if "connection" in error_message.lower() and "database" in error_message.lower():
        return DatabaseConnectionError(error)

    if "pydantic" in error_type.lower() or "validation" in error_type.lower():
        return JobValidationError(
            job_name=context.get("job_name", "unknown") if context else "unknown",
            validation_errors=[error_message],
            provided_args=context.get("args", {}) if context else {},
        )

    # Generic FastJob error for unhandled exceptions
    suggestions = [
        "Check application logs for more details",
        "Verify system requirements and dependencies",
        "Ensure proper configuration is in place",
        "Contact support if issue persists",
    ]

    return FastJobError(
        message=f"Unexpected error: {error_message}",
        error_code="UNEXPECTED_ERROR",
        context={"original_error_type": error_type, **(context or {})},
        suggestions=suggestions,
        documentation_url="https://docs.fastjob.dev/troubleshooting",
    )
