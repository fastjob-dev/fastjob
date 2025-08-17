"""
Test suite for errors.py module - comprehensive coverage for FastJob exception handling.
"""

import pytest

from fastjob.errors import (
    ConfigurationError,
    DatabaseConnectionError,
    FastJobError,
    JobExecutionError,
    JobNotFoundError,
    JobValidationError,
    MigrationError,
    QueueError,
    SchedulingError,
    WorkerError,
    create_user_friendly_error,
)


class TestFastJobError:
    """Test base FastJobError class."""

    def test_basic_error_creation(self):
        """Test basic error creation."""
        error = FastJobError(
            message="Test error",
            error_code="TEST_ERROR",
        )

        assert error.message == "Test error"
        assert error.error_code == "TEST_ERROR"
        assert error.context == {}
        assert error.suggestions == []
        assert error.documentation_url is None
        assert "FastJob Error [TEST_ERROR]: Test error" in str(error)

    def test_error_with_context(self):
        """Test error with context information."""
        context = {"user_id": 123, "operation": "test_op"}
        error = FastJobError(
            message="Context error",
            error_code="CONTEXT_ERROR",
            context=context,
        )

        assert error.context == context
        error_str = str(error)
        assert "Context:" in error_str
        assert "user_id: 123" in error_str
        assert "operation: test_op" in error_str

    def test_error_with_suggestions(self):
        """Test error with suggestions."""
        suggestions = ["Check configuration", "Restart service"]
        error = FastJobError(
            message="Suggestion error",
            error_code="SUGGESTION_ERROR",
            suggestions=suggestions,
        )

        assert error.suggestions == suggestions
        error_str = str(error)
        assert "Suggestions:" in error_str
        assert "• Check configuration" in error_str
        assert "• Restart service" in error_str

    def test_error_with_documentation_url(self):
        """Test error with documentation URL."""
        doc_url = "https://docs.fastjob.dev/troubleshooting"
        error = FastJobError(
            message="Documentation error",
            error_code="DOC_ERROR",
            documentation_url=doc_url,
        )

        assert error.documentation_url == doc_url
        error_str = str(error)
        assert f"Documentation: {doc_url}" in error_str

    def test_error_complete_formatting(self):
        """Test error with all components for complete formatting."""
        error = FastJobError(
            message="Complete error",
            error_code="COMPLETE_ERROR",
            context={"key": "value"},
            suggestions=["Suggestion 1", "Suggestion 2"],
            documentation_url="https://docs.example.com",
        )

        error_str = str(error)
        assert "FastJob Error [COMPLETE_ERROR]: Complete error" in error_str
        assert "Context:" in error_str
        assert "key: value" in error_str
        assert "Suggestions:" in error_str
        assert "• Suggestion 1" in error_str
        assert "• Suggestion 2" in error_str
        assert "Documentation: https://docs.example.com" in error_str


class TestDatabaseConnectionError:
    """Test DatabaseConnectionError."""

    def test_database_connection_error_basic(self):
        """Test basic database connection error."""
        original_error = ConnectionError("Connection refused")
        error = DatabaseConnectionError(original_error)

        assert error.error_code == "DB_CONNECTION_FAILED"
        assert "Failed to connect to PostgreSQL database" in error.message
        assert error.context["original_error"] == "Connection refused"
        assert error.context["error_type"] == "ConnectionError"
        suggestions_text = " ".join(error.suggestions)
        assert "Verify that PostgreSQL is running" in suggestions_text

    def test_database_connection_error_with_url(self):
        """Test database connection error with URL masking."""
        original_error = ConnectionError("Connection refused")
        database_url = "postgresql://user:secret123@localhost:5432/fastjob"
        error = DatabaseConnectionError(original_error, database_url)

        assert "secret123" not in error.context["database_url"]
        assert "user:***@localhost" in error.context["database_url"]

    def test_mask_database_url_method(self):
        """Test URL masking method."""
        # Test various URL formats
        urls_and_expected = [
            (
                "postgresql://user:password@localhost:5432/db",
                "postgresql://user:***@localhost:5432/db",
            ),
            (
                "postgres://admin:secret123@db.example.com/prod",
                "postgres://admin:***@db.example.com/prod",
            ),
            (
                "postgresql://user@localhost/db",  # No password
                "postgresql://user@localhost/db",
            ),
        ]

        for url, expected in urls_and_expected:
            masked = DatabaseConnectionError._mask_database_url(url)
            assert masked == expected


class TestJobNotFoundError:
    """Test JobNotFoundError."""

    def test_job_not_found_error_basic(self):
        """Test basic job not found error."""
        error = JobNotFoundError("send_email")

        assert error.error_code == "JOB_NOT_FOUND"
        assert "Job function 'send_email' not found" in error.message
        assert error.context["job_name"] == "send_email"
        suggestions_text = " ".join(error.suggestions)
        assert "Ensure job function 'send_email' is decorated" in suggestions_text

    def test_job_not_found_error_with_available_jobs(self):
        """Test job not found error with available jobs list."""
        available_jobs = ["job1", "job2", "job3"]
        error = JobNotFoundError("missing_job", available_jobs)

        assert error.context["available_jobs"] == available_jobs
        suggestions_text = " ".join(error.suggestions)
        assert "Available jobs: job1, job2, job3" in suggestions_text


class TestJobValidationError:
    """Test JobValidationError."""

    def test_job_validation_error_basic(self):
        """Test basic job validation error."""
        validation_errors = [
            "Missing required field 'email'",
            "Invalid type for 'count'",
        ]
        provided_args = {"name": "test", "count": "invalid"}

        error = JobValidationError("send_email", validation_errors, provided_args)

        assert error.error_code == "JOB_VALIDATION_FAILED"
        assert "send_email" in error.message
        assert "Missing required field 'email'" in error.message
        assert error.context["job_name"] == "send_email"
        assert error.context["validation_errors"] == validation_errors
        assert error.context["provided_args"] == ["name", "count"]

    def test_job_validation_error_truncates_long_values(self):
        """Test that long argument values are truncated."""
        long_value = "x" * 200
        validation_errors = ["Invalid data"]
        provided_args = {"data": long_value}

        error = JobValidationError("test_job", validation_errors, provided_args)

        # Should be truncated to 100 characters
        assert len(error.context["provided_values"]["data"]) == 100
        assert error.context["provided_values"]["data"] == "x" * 100


class TestJobExecutionError:
    """Test JobExecutionError."""

    def test_job_execution_error_basic(self):
        """Test basic job execution error."""
        original_error = ValueError("Invalid input")

        error = JobExecutionError(
            job_name="process_data",
            job_id="123e4567-e89b-12d3-a456-426614174000",
            original_error=original_error,
            attempt=2,
            max_attempts=3,
        )

        assert error.error_code == "JOB_EXECUTION_FAILED"
        assert "process_data" in error.message
        assert "attempt 2/3" in error.message
        assert "Invalid input" in error.message
        assert error.context["job_name"] == "process_data"
        assert error.context["attempt"] == 2
        assert error.context["max_attempts"] == 3
        assert error.context["error_type"] == "ValueError"

    def test_job_execution_error_with_args(self):
        """Test job execution error with job arguments."""
        original_error = RuntimeError("Processing failed")
        args = {"user_id": 123, "data": "test data"}

        error = JobExecutionError(
            job_name="test_job",
            job_id="test-id",
            original_error=original_error,
            attempt=1,
            max_attempts=3,
            args=args,
        )

        assert "job_args" in error.context
        assert error.context["job_args"]["user_id"] == "123"
        assert error.context["job_args"]["data"] == "test data"

    def test_job_execution_error_retry_message(self):
        """Test retry message for non-final attempts."""
        original_error = Exception("Retry me")

        error = JobExecutionError(
            job_name="retry_job",
            job_id="retry-id",
            original_error=original_error,
            attempt=1,
            max_attempts=3,
        )

        suggestions_text = " ".join(error.suggestions)
        assert "Job will be retried (attempt 2/3)" in suggestions_text

    def test_job_execution_error_final_attempt(self):
        """Test dead letter message for final attempt."""
        original_error = Exception("Final failure")

        error = JobExecutionError(
            job_name="final_job",
            job_id="final-id",
            original_error=original_error,
            attempt=3,
            max_attempts=3,
        )

        suggestions_text = " ".join(error.suggestions)
        assert "Job will be moved to dead letter queue" in suggestions_text

    def test_job_execution_error_truncates_long_args(self):
        """Test that long argument values are truncated."""
        original_error = Exception("Error")
        long_data = "x" * 100
        args = {"data": long_data}

        error = JobExecutionError(
            job_name="test_job",
            job_id="test-id",
            original_error=original_error,
            attempt=1,
            max_attempts=1,
            args=args,
        )

        # Should be truncated to 50 characters
        assert len(error.context["job_args"]["data"]) == 50
        assert error.context["job_args"]["data"] == "x" * 50


class TestQueueError:
    """Test QueueError."""

    def test_queue_error_basic(self):
        """Test basic queue error."""
        error = QueueError(
            operation="enqueue",
            queue_name="email_queue",
            reason="Queue is full",
        )

        assert error.error_code == "QUEUE_OPERATION_FAILED"
        assert "enqueue" in error.message
        assert "email_queue" in error.message
        assert "Queue is full" in error.message
        assert error.context["operation"] == "enqueue"
        assert error.context["queue_name"] == "email_queue"
        assert error.context["reason"] == "Queue is full"

    def test_queue_error_with_details(self):
        """Test queue error with additional details."""
        details = {"queue_size": 1000, "max_size": 1000}

        error = QueueError(
            operation="enqueue",
            queue_name="test_queue",
            reason="Size limit exceeded",
            details=details,
        )

        assert error.context["queue_size"] == 1000
        assert error.context["max_size"] == 1000


class TestWorkerError:
    """Test WorkerError."""

    def test_worker_error_basic(self):
        """Test basic worker error."""
        error = WorkerError(
            operation="start",
            reason="Port already in use",
        )

        assert error.error_code == "WORKER_OPERATION_FAILED"
        assert "start" in error.message
        assert "Port already in use" in error.message
        assert error.context["operation"] == "start"
        assert error.context["reason"] == "Port already in use"

    def test_worker_error_with_config(self):
        """Test worker error with worker configuration."""
        worker_config = {"concurrency": 4, "queues": ["default"]}

        error = WorkerError(
            operation="configure",
            reason="Invalid configuration",
            worker_config=worker_config,
        )

        assert error.context["worker_config"] == worker_config


class TestConfigurationError:
    """Test ConfigurationError."""

    def test_configuration_error_basic(self):
        """Test basic configuration error."""
        error = ConfigurationError(
            setting="database_url",
            value=None,
            reason="Required setting is missing",
        )

        assert error.error_code == "CONFIGURATION_ERROR"
        assert "database_url" in error.message
        assert "Required setting is missing" in error.message
        assert error.context["setting"] == "database_url"
        assert error.context["provided_value"] == "None"
        assert error.context["reason"] == "Required setting is missing"

    def test_configuration_error_with_expected(self):
        """Test configuration error with expected format."""
        error = ConfigurationError(
            setting="retry_attempts",
            value="invalid",
            reason="Must be an integer",
            expected="positive integer (1-10)",
        )

        assert error.context["expected"] == "positive integer (1-10)"
        assert "Expected format: positive integer (1-10)" in error.suggestions

    def test_configuration_error_value_conversion(self):
        """Test that non-None values are converted to string."""
        error = ConfigurationError(
            setting="port",
            value=8080,
            reason="Port is already in use",
        )

        assert error.context["provided_value"] == "8080"


class TestSchedulingError:
    """Test SchedulingError."""

    def test_scheduling_error_basic(self):
        """Test basic scheduling error."""
        error = SchedulingError(
            job_name="send_report",
            schedule_time="2023-13-01 10:00:00",  # Invalid month
            reason="Invalid date format",
        )

        assert error.error_code == "SCHEDULING_FAILED"
        assert "send_report" in error.message
        assert "2023-13-01 10:00:00" in error.message
        assert "Invalid date format" in error.message
        assert error.context["job_name"] == "send_report"
        assert error.context["schedule_time"] == "2023-13-01 10:00:00"
        assert error.context["reason"] == "Invalid date format"


class TestMigrationError:
    """Test MigrationError."""

    def test_migration_error_basic(self):
        """Test basic migration error."""
        error = MigrationError(
            migration_step="create_jobs_table",
            reason="Table already exists",
        )

        assert error.error_code == "MIGRATION_FAILED"
        assert "create_jobs_table" in error.message
        assert "Table already exists" in error.message
        assert error.context["migration_step"] == "create_jobs_table"
        assert error.context["reason"] == "Table already exists"

    def test_migration_error_with_database_info(self):
        """Test migration error with database information."""
        database_info = {"version": "13.2", "encoding": "UTF8"}

        error = MigrationError(
            migration_step="add_index",
            reason="Insufficient privileges",
            database_info=database_info,
        )

        assert error.context["version"] == "13.2"
        assert error.context["encoding"] == "UTF8"


class TestCreateUserFriendlyError:
    """Test create_user_friendly_error function."""

    def test_fastjob_error_passthrough(self):
        """Test that FastJobError instances are returned as-is."""
        original_error = JobNotFoundError("test_job")

        result = create_user_friendly_error(original_error)

        assert result is original_error

    def test_database_connection_error_detection(self):
        """Test automatic detection of database connection errors."""
        original_error = Exception("Connection to database failed")

        result = create_user_friendly_error(original_error)

        assert isinstance(result, DatabaseConnectionError)

    def test_pydantic_validation_error_detection(self):
        """Test automatic detection of Pydantic validation errors."""

        # Create a custom error class to simulate Pydantic error
        class ValidationError(Exception):
            pass

        original_error = ValidationError("Validation failed")

        context = {"job_name": "test_job", "args": {"field": "value"}}
        result = create_user_friendly_error(original_error, context)

        assert isinstance(result, JobValidationError)
        assert result.context["job_name"] == "test_job"

    def test_pydantic_validation_error_by_type_name(self):
        """Test detection by 'pydantic' in error type name."""

        class PydanticCustomError(Exception):
            pass

        original_error = PydanticCustomError("Pydantic validation failed")

        result = create_user_friendly_error(original_error)

        assert isinstance(result, JobValidationError)

    def test_validation_error_by_type_name(self):
        """Test detection by 'validation' in error type name."""

        class CustomValidationError(Exception):
            pass

        original_error = CustomValidationError("Custom validation failed")

        result = create_user_friendly_error(original_error)

        assert isinstance(result, JobValidationError)

    def test_generic_error_conversion(self):
        """Test conversion of generic errors to FastJobError."""
        original_error = RuntimeError("Something went wrong")
        context = {"additional": "info"}

        result = create_user_friendly_error(original_error, context)

        assert isinstance(result, FastJobError)
        assert result.error_code == "UNEXPECTED_ERROR"
        assert "Something went wrong" in result.message
        assert result.context["original_error_type"] == "RuntimeError"
        assert result.context["additional"] == "info"

    def test_create_user_friendly_error_no_context(self):
        """Test error conversion without context."""
        original_error = ValueError("Invalid value")

        result = create_user_friendly_error(original_error)

        assert isinstance(result, FastJobError)
        assert result.context["original_error_type"] == "ValueError"
        assert "additional" not in result.context


class TestErrorInheritance:
    """Test that all error classes properly inherit from FastJobError."""

    def test_all_errors_inherit_from_fastjob_error(self):
        """Test that all custom error classes inherit from FastJobError."""
        error_classes = [
            DatabaseConnectionError,
            JobNotFoundError,
            JobValidationError,
            JobExecutionError,
            QueueError,
            WorkerError,
            ConfigurationError,
            SchedulingError,
            MigrationError,
        ]

        for error_class in error_classes:
            assert issubclass(error_class, FastJobError)
            assert issubclass(error_class, Exception)

    def test_error_can_be_caught_as_fastjob_error(self):
        """Test that specific errors can be caught as FastJobError."""
        with pytest.raises(FastJobError):
            raise JobNotFoundError("test_job")

    def test_error_can_be_caught_as_exception(self):
        """Test that FastJob errors can be caught as generic Exception."""
        with pytest.raises(Exception):
            raise DatabaseConnectionError(ConnectionError("test"))


class TestErrorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_context_and_suggestions(self):
        """Test error with empty context and suggestions."""
        error = FastJobError(
            message="Test",
            error_code="TEST",
            context={},
            suggestions=[],
        )

        # Should not include empty sections in formatted message
        error_str = str(error)
        assert "Context:" not in error_str
        assert "Suggestions:" not in error_str

    def test_none_values_in_context(self):
        """Test handling of None values in context."""
        context = {"key1": None, "key2": "value"}
        error = FastJobError(
            message="Test",
            error_code="TEST",
            context=context,
        )

        error_str = str(error)
        assert "key1: None" in error_str
        assert "key2: value" in error_str

    def test_very_long_error_message(self):
        """Test handling of very long error messages."""
        long_message = "x" * 1000
        error = FastJobError(
            message=long_message,
            error_code="LONG_ERROR",
        )

        # Should not crash and should include the full message
        error_str = str(error)
        assert long_message in error_str

    def test_special_characters_in_message(self):
        """Test handling of special characters in error messages."""
        special_message = (
            "Error with 'quotes', \"double quotes\", and \nnewlines\t tabs"
        )
        error = FastJobError(
            message=special_message,
            error_code="SPECIAL_CHARS",
        )

        error_str = str(error)
        assert special_message in error_str

    def test_unicode_characters(self):
        """Test handling of Unicode characters."""
        unicode_message = "Error with émojis 🚀 and ñice characters"
        error = FastJobError(
            message=unicode_message,
            error_code="UNICODE_ERROR",
        )

        error_str = str(error)
        assert unicode_message in error_str


class TestErrorSerialization:
    """Test error serialization and representation."""

    def test_error_repr(self):
        """Test error __repr__ method."""
        error = FastJobError("Test error", "TEST_CODE")

        # Should be able to create repr without errors
        repr_str = repr(error)
        assert "FastJobError" in repr_str

    def test_error_with_complex_context(self):
        """Test error with complex context objects."""
        complex_context = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "tuple": (4, 5, 6),
        }

        error = FastJobError(
            message="Complex context",
            error_code="COMPLEX",
            context=complex_context,
        )

        # Should handle complex objects in context
        error_str = str(error)
        assert "nested:" in error_str
        assert "list:" in error_str
        assert "tuple:" in error_str
