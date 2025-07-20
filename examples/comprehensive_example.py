"""
Comprehensive FastJob example demonstrating all features
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pydantic import BaseModel

import fastjob


# Configure structured logging
fastjob_logger = fastjob.logging.setup_logging(level="INFO", format_type="structured")

# Define job argument models
class EmailArgs(BaseModel):
    to: str
    subject: str
    body: str
    priority: str = "normal"

class ProcessOrderArgs(BaseModel):
    order_id: int
    user_id: int
    items: list[str]
    total_amount: float


# Define jobs with different priorities and queues
@fastjob.job(retries=3, args_model=EmailArgs, priority=10, queue="email")
async def send_email(to: str, subject: str, body: str, priority: str = "normal"):
    """Send an email - high priority queue"""
    print(f"📧 Sending {priority} email to {to}: {subject}")
    await asyncio.sleep(0.5)  # Simulate email sending
    return f"Email sent to {to}"

@fastjob.job(retries=5, args_model=ProcessOrderArgs, priority=50, queue="orders")
async def process_order(order_id: int, user_id: int, items: list[str], total_amount: float):
    """Process an order - medium priority"""
    print(f"🛒 Processing order #{order_id} for user {user_id} - ${total_amount}")
    await asyncio.sleep(1.0)  # Simulate order processing
    return f"Order {order_id} processed"

@fastjob.job(retries=2, priority=100, queue="analytics")
async def generate_report(report_type: str, date_range: str):
    """Generate analytics report - low priority"""
    print(f"📊 Generating {report_type} report for {date_range}")
    await asyncio.sleep(2.0)  # Simulate report generation
    return f"Report {report_type} generated"

@fastjob.job(retries=1, priority=1, queue="critical")
async def critical_task(task_id: str, data: dict):
    """Critical system task - highest priority"""
    print(f"🚨 Processing critical task: {task_id}")
    await asyncio.sleep(0.1)
    return f"Critical task {task_id} completed"

@fastjob.job(retries=3)
async def flaky_task(task_id: str, fail_rate: float = 0.3):
    """A task that sometimes fails"""
    import random
    if random.random() < fail_rate:
        raise Exception(f"Task {task_id} failed randomly")
    print(f"✅ Flaky task {task_id} succeeded")
    return f"Task {task_id} completed"


async def main():
    """Demonstrate all FastJob features"""
    print("🚀 FastJob Comprehensive Example")
    print("=" * 50)
    
    # 1. Basic job enqueueing
    print("\n1. Basic Job Enqueueing:")
    job_id1 = await fastjob.enqueue(
        send_email,
        to="user@example.com",
        subject="Welcome!",
        body="Thanks for signing up!"
    )
    print(f"   Enqueued email job: {job_id1}")
    
    # 2. Job with validation
    print("\n2. Job with Pydantic Validation:")
    job_id2 = await fastjob.enqueue(
        process_order,
        order_id=12345,
        user_id=67890,
        items=["laptop", "mouse", "keyboard"],
        total_amount=1299.99
    )
    print(f"   Enqueued order job: {job_id2}")
    
    # 3. Job with custom priority
    print("\n3. High Priority Job:")
    job_id3 = await fastjob.enqueue(
        critical_task,
        priority=1,  # Override default priority
        task_id="CRIT-001",
        data={"urgency": "high", "system": "payment"}
    )
    print(f"   Enqueued critical job: {job_id3}")
    
    # 4. Job on specific queue
    print("\n4. Queue-Specific Job:")
    job_id4 = await fastjob.enqueue(
        generate_report,
        queue="analytics",  # Override default queue
        report_type="sales",
        date_range="2024-01-01 to 2024-01-31"
    )
    print(f"   Enqueued analytics job: {job_id4}")
    
    # 5. Scheduled job (future execution)
    print("\n5. Scheduled Job:")
    future_time = datetime.now() + timedelta(seconds=10)
    job_id5 = await fastjob.schedule(send_email).at(future_time).enqueue(
        to="admin@example.com",
        subject="Scheduled Report",
        body="Your scheduled report is ready"
    )
    print(f"   Scheduled job for {future_time}: {job_id5}")
    
    # 6. Job scheduled with fluent interface
    print("\n6. Fluent Scheduling:")
    job_id6 = await fastjob.schedule(generate_report).in_minutes(2).with_priority(20).enqueue(
        report_type="user_activity",
        date_range="last_7_days"
    )
    print(f"   Job scheduled for 2 minutes: {job_id6}")
    
    # 7. Convenience scheduling functions
    print("\n7. Convenience Scheduling:")
    job_id7 = await fastjob.schedule_in(
        flaky_task, 5,  # 5 seconds from now
        task_id="FLAKY-001",
        fail_rate=0.8  # High failure rate to demonstrate retries
    )
    print(f"   Flaky job scheduled: {job_id7}")
    
    # 8. Start embedded worker for immediate processing
    print("\n8. Starting Embedded Worker...")
    fastjob.start_embedded_worker()
    
    # Let some jobs process
    print("   Processing jobs for 15 seconds...")
    await asyncio.sleep(15)
    
    # 9. Get metrics
    print("\n9. Job Metrics:")
    from fastjob.metrics import get_metrics_collector
    metrics = get_metrics_collector()
    system_metrics = await metrics.get_system_metrics(time_window_hours=1)
    
    print(f"   Total jobs: {system_metrics.total_jobs}")
    print(f"   Completed: {system_metrics.completed_jobs}")
    print(f"   Queued: {system_metrics.queued_jobs}")
    print(f"   Success rate: {system_metrics.success_rate}%")
    print(f"   Avg processing time: {system_metrics.avg_processing_time_ms}ms")
    
    # 10. Check dead letter queue
    print("\n10. Dead Letter Queue:")
    from fastjob.dead_letter import get_dead_letter_queue
    dlq = get_dead_letter_queue()
    dead_jobs = await dlq.get_dead_letter_jobs(limit=10)
    dlq_stats = await dlq.get_dead_letter_stats()
    
    print(f"    Dead letter jobs: {dlq_stats['total_dead_jobs']}")
    if dead_jobs:
        print("    Recent dead letter jobs:")
        for job in dead_jobs[:3]:
            print(f"      - {job['job_name']} (attempts: {job['attempts']})")
    
    # Stop worker
    await fastjob.stop_embedded_worker()
    print("\n✅ Example completed!")
    print("\nTo explore more:")
    print("- Run 'fastjob dashboard' to see the web interface")
    print("- Run 'fastjob run-worker --concurrency 4' for production")
    print("- Check the logs above for structured logging output")


if __name__ == "__main__":
    asyncio.run(main())