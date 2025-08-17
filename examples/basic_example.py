"""
Basic FastJob Example - Core Functionality
This example demonstrates the essential features of FastJob base package.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List

from pydantic import BaseModel

import fastjob


# Define job argument models for type safety
class EmailData(BaseModel):
    to: str
    subject: str
    body: str


class ProcessingData(BaseModel):
    task_id: int
    data: List[str]


# Basic job - simple function
@fastjob.job()
async def simple_task(message: str) -> str:
    """A simple job that processes a message."""
    print(f"Processing message: {message}")
    await asyncio.sleep(1)  # Simulate work
    return f"Processed: {message}"


# Job with validation using Pydantic model
@fastjob.job(retries=3, args_model=EmailData)
async def send_email(to: str, subject: str, body: str) -> None:
    """Send an email notification."""
    print(f"Sending email to {to}")
    print(f"Subject: {subject}")
    print(f"Body: {body}")

    # Simulate email sending
    await asyncio.sleep(0.5)
    print(f"✓ Email sent successfully to {to}")


# Job with priority and custom queue
@fastjob.job(priority=10, queue="urgent", retries=5)
async def urgent_processing(task_id: int, data: List[str]) -> dict:
    """Process urgent data with high priority."""
    print(f"🚨 Processing urgent task {task_id}")

    results = []
    for item in data:
        # Simulate processing each item
        await asyncio.sleep(0.1)
        result = f"processed_{item}"
        results.append(result)
        print(f"  ✓ Processed: {item} -> {result}")

    return {
        "task_id": task_id,
        "processed_count": len(results),
        "results": results,
        "completed_at": datetime.now().isoformat(),
    }


# Job that might fail (demonstrates retry mechanism)
@fastjob.job(retries=2, queue="unreliable")
async def unreliable_task(attempt_number: int) -> str:
    """A task that fails sometimes to demonstrate retry logic."""
    print(f"Attempt #{attempt_number} - This task might fail...")

    # Fail on first two attempts, succeed on third
    if attempt_number < 3:
        print(f"💥 Task failed on attempt {attempt_number}")
        raise Exception(f"Simulated failure on attempt {attempt_number}")

    print("✓ Task succeeded!")
    return f"Success after {attempt_number} attempts"


# Scheduled job
@fastjob.job()
async def scheduled_report() -> dict:
    """Generate a scheduled report."""
    print("📊 Generating daily report...")

    # Simulate report generation
    await asyncio.sleep(1)

    report = {
        "generated_at": datetime.now().isoformat(),
        "total_jobs": 42,
        "successful_jobs": 40,
        "failed_jobs": 2,
        "report_type": "daily_summary",
    }

    print(f"✓ Report generated: {report}")
    return report


async def main():
    """
    Main example function demonstrating FastJob usage.
    """
    print("🚀 FastJob Basic Example")
    print("=" * 50)

    # Start embedded worker for this example
    print("Starting embedded worker...")
    fastjob.start_embedded_worker()

    try:
        # Example 1: Simple job
        print("\n1. Enqueuing simple task...")
        job_id = await fastjob.enqueue(simple_task, message="Hello FastJob!")
        print(f"   Job ID: {job_id}")

        # Example 2: Email job with validation
        print("\n2. Enqueuing email job...")
        job_id = await fastjob.enqueue(
            send_email,
            to="user@example.com",
            subject="Welcome to FastJob!",
            body="Thank you for trying FastJob.",
        )
        print(f"   Job ID: {job_id}")

        # Example 3: Urgent processing
        print("\n3. Enqueuing urgent processing job...")
        job_id = await fastjob.enqueue(
            urgent_processing, task_id=123, data=["item1", "item2", "item3"]
        )
        print(f"   Job ID: {job_id}")

        # Example 4: Job with custom priority (override default)
        print("\n4. Enqueuing high priority job...")
        job_id = await fastjob.enqueue(
            simple_task,
            priority=1,  # Override job's default priority
            message="High priority task",
        )
        print(f"   Job ID: {job_id}")

        # Example 5: Scheduled job (future execution)
        print("\n5. Scheduling job for future execution...")
        scheduled_time = datetime.now() + timedelta(seconds=5)
        job_id = await fastjob.enqueue(scheduled_report, scheduled_at=scheduled_time)
        print(f"   Job ID: {job_id}")
        print(f"   Scheduled for: {scheduled_time}")

        # Example 6: Unreliable job (will retry)
        print("\n6. Enqueuing unreliable job (will demonstrate retries)...")
        job_id = await fastjob.enqueue(unreliable_task, attempt_number=1)
        print(f"   Job ID: {job_id}")

        # Wait for jobs to process
        print("\n⏳ Waiting for jobs to complete...")
        await asyncio.sleep(10)

        print("\n✅ Example completed!")
        print("\nTo see job results in production, use:")
        print("  fastjob run-worker --concurrency 4")

    finally:
        # Stop embedded worker
        print("\nStopping embedded worker...")
        await fastjob.stop_embedded_worker()


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())
