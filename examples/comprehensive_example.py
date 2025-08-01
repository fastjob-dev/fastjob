"""
Comprehensive FastJob example demonstrating all features

This example shows both Global API and Instance API patterns:
- Global API: Simple single-database setup (great for getting started)
- Instance API: Multi-database setup (perfect for microservices)

Choose the approach that fits your architecture:
- Single application with one job queue → Global API
- Multiple services with separate databases → Instance API
- Multi-tenant application → Instance API with database per tenant
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from pydantic import BaseModel

import fastjob
from fastjob import FastJob


# Configure basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


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
async def process_order(
    order_id: int, user_id: int, items: list[str], total_amount: float
):
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


# ========================================
# INSTANCE API EXAMPLES
# ========================================

# Create separate FastJob instances for different services
analytics_service = FastJob(
    database_url=os.environ.get("ANALYTICS_DATABASE_URL", "postgresql://localhost/analytics_service"),
    service_name="analytics"
)

user_service = FastJob(
    database_url=os.environ.get("USER_DATABASE_URL", "postgresql://localhost/user_service"), 
    service_name="users"
)

# Instance API jobs - registered with specific instances
@analytics_service.job(queue="events", priority=20)
async def track_user_event(event_name: str, user_id: str, properties: dict) -> dict:
    """Track user analytics event - Instance API"""
    print(f"📊 [ANALYTICS] Tracking event: {event_name} for user {user_id}")
    await asyncio.sleep(0.3)
    
    return {
        "event_name": event_name,
        "user_id": user_id,
        "properties": properties,
        "tracked_at": datetime.now().isoformat(),
        "service": "analytics"
    }


@user_service.job(queue="profile_updates", retries=2)
async def update_user_profile(user_id: str, profile_data: dict) -> dict:
    """Update user profile - Instance API"""
    print(f"👤 [USER_SERVICE] Updating profile for user: {user_id}")
    await asyncio.sleep(0.5)
    
    return {
        "user_id": user_id,
        "profile_data": profile_data,
        "updated_at": datetime.now().isoformat(),
        "service": "users"
    }


@user_service.job(queue="cross_service_workflows")
async def user_activity_workflow(user_id: str, activity_type: str) -> dict:
    """Cross-service workflow using Instance API"""
    print(f"🔄 [WORKFLOW] Starting activity workflow for user: {user_id}")
    
    # Update user profile (same service)
    profile_job = await user_service.enqueue(
        update_user_profile,
        user_id=user_id,
        profile_data={"last_activity": activity_type, "timestamp": datetime.now().isoformat()}
    )
    
    # Track analytics event (different service)
    analytics_job = await analytics_service.enqueue(
        track_user_event,
        event_name=f"user_{activity_type}",
        user_id=user_id,
        properties={"workflow": "user_activity", "initiated_by": "system"}
    )
    
    return {
        "workflow_id": f"activity_{user_id}_{int(datetime.now().timestamp())}",
        "user_id": user_id,
        "activity_type": activity_type,
        "jobs": {
            "profile_update": profile_job,
            "analytics_tracking": analytics_job
        },
        "status": "initiated"
    }


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
        body="Thanks for signing up!",
    )
    print(f"   Enqueued email job: {job_id1}")

    # 2. Job with validation
    print("\n2. Job with Pydantic Validation:")
    job_id2 = await fastjob.enqueue(
        process_order,
        order_id=12345,
        user_id=67890,
        items=["laptop", "mouse", "keyboard"],
        total_amount=1299.99,
    )
    print(f"   Enqueued order job: {job_id2}")

    # 3. Job with custom priority
    print("\n3. High Priority Job:")
    job_id3 = await fastjob.enqueue(
        critical_task,
        priority=1,  # Override default priority
        task_id="CRIT-001",
        data={"urgency": "high", "system": "payment"},
    )
    print(f"   Enqueued critical job: {job_id3}")

    # 4. Job on specific queue
    print("\n4. Queue-Specific Job:")
    job_id4 = await fastjob.enqueue(
        generate_report,
        queue="analytics",  # Override default queue
        report_type="sales",
        date_range="2025-01-01 to 2025-01-31",
    )
    print(f"   Enqueued analytics job: {job_id4}")

    # 5. Scheduled job (future execution)
    print("\n5. Scheduled Job:")
    future_time = datetime.now() + timedelta(seconds=10)
    job_id5 = await fastjob.schedule(
        send_email,
        run_at=future_time,
        to="admin@example.com",
        subject="Scheduled Report",
        body="Your scheduled report is ready",
    )
    print(f"   Scheduled job for {future_time}: {job_id5}")

    # 6. Job scheduled with delay
    print("\n6. Delayed Scheduling:")
    job_id6 = await fastjob.schedule(
        generate_report,
        run_in=120,  # 2 minutes (120 seconds)
        priority=20,
        report_type="user_activity",
        date_range="last_7_days",
    )
    print(f"   Job scheduled for 2 minutes: {job_id6}")

    # 7. Convenience scheduling functions
    print("\n7. Convenience Scheduling:")
    job_id7 = await fastjob.schedule(
        flaky_task,
        run_in=5,  # 5 seconds from now
        task_id="FLAKY-001",
        fail_rate=0.8,  # High failure rate to demonstrate retries
    )
    print(f"   Flaky job scheduled: {job_id7}")

    # 8. Start embedded worker for immediate processing
    print("\n8. Starting Embedded Worker...")
    fastjob.start_embedded_worker()

    # Let some jobs process
    print("   Processing jobs for 15 seconds...")
    await asyncio.sleep(15)

    # 9. Get basic queue statistics
    print("\n9. Queue Statistics:")
    queue_stats = await fastjob.get_queue_stats()

    if queue_stats:
        for queue in queue_stats:
            print(f"   Queue '{queue['queue']}':")
            print(f"     Total jobs: {queue['total_jobs']}")
            print(f"     Queued: {queue['queued']}")
            print(f"     Done: {queue['done']}")
            print(f"     Failed: {queue['failed']}")
            print(f"     Cancelled: {queue['cancelled']}")
    else:
        print("   No queue statistics available yet")

    # 10. List recent jobs
    print("\n10. Recent Jobs:")
    recent_jobs = await fastjob.list_jobs(limit=5)

    if recent_jobs:
        print("   Recent jobs:")
        for job in recent_jobs:
            print(f"     - {job['job_name']}: {job['status']} (queue: {job['queue']})")
    else:
        print("   No jobs found")

    # Stop Global API worker
    await fastjob.stop_embedded_worker()
    
    # ========================================
    # INSTANCE API DEMONSTRATION
    # ========================================
    
    print("\n" + "="*60)
    print("INSTANCE API DEMONSTRATION")
    print("="*60)
    print("Using separate databases for different services")
    
    # Start embedded workers for Instance API services
    print("\n11. Starting Instance API Workers...")
    analytics_service.start_embedded_worker()
    user_service.start_embedded_worker()
    
    try:
        # Instance API job examples
        print("\n12. Analytics Service Job (Instance API):")
        analytics_job = await analytics_service.enqueue(
            track_user_event,
            event_name="page_view",
            user_id="user_123",
            properties={"page": "/dashboard", "duration": 45}
        )
        print(f"   Analytics job ID: {analytics_job}")
        
        print("\n13. User Service Job (Instance API):")
        user_job = await user_service.enqueue(
            update_user_profile,
            user_id="user_123",
            profile_data={"theme": "dark", "language": "en"}
        )
        print(f"   User service job ID: {user_job}")
        
        print("\n14. Cross-Service Workflow (Instance API):")
        workflow_job = await user_service.enqueue(
            user_activity_workflow,
            user_id="user_456",
            activity_type="login"
        )
        print(f"   Workflow job ID: {workflow_job}")
        
        # Let Instance API jobs process
        print("\n   Processing Instance API jobs for 8 seconds...")
        await asyncio.sleep(8)
        
        # Show service-specific statistics
        print("\n15. Instance API Service Statistics:")
        
        analytics_stats = await analytics_service.get_queue_stats()
        user_stats = await user_service.get_queue_stats()
        
        print("   Analytics Service:")
        if analytics_stats:
            for queue in analytics_stats:
                print(f"     Queue '{queue['queue']}': {queue['total_jobs']} total, {queue['done']} done")
        else:
            print("     No statistics available yet")
            
        print("   User Service:")
        if user_stats:
            for queue in user_stats:
                print(f"     Queue '{queue['queue']}': {queue['total_jobs']} total, {queue['done']} done")
        else:
            print("     No statistics available yet")
        
    finally:
        # Stop Instance API workers and close connections
        print("\n   Stopping Instance API workers...")
        await analytics_service.stop_embedded_worker()
        await user_service.stop_embedded_worker()
        
        await analytics_service.close()
        await user_service.close()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print("✅ Global API: Perfect for single-service applications")
    print("✅ Instance API: Perfect for microservices and multi-tenant apps")
    print("✅ Both APIs demonstrated successfully!")
    
    print("\n✅ Comprehensive example completed!")
    print("\nAPI Comparison:")
    print("  Global API (single database):")
    print("    - Simple setup with fastjob.job() and fastjob.enqueue()")
    print("    - All jobs share the same database")
    print("    - Perfect for single applications")
    print("  Instance API (multiple databases):")
    print("    - Create FastJob instances with separate database URLs")
    print("    - Complete isolation between services")
    print("    - Perfect for microservices architecture")
    
    print("\nTo explore more:")
    print("- Run 'fastjob status' to see Global API queue statistics")
    print("- Run 'fastjob status --database-url $SERVICE_DB' for Instance API")
    print("- Run 'fastjob worker --concurrency 4' for Global API production")
    print("- Run 'fastjob worker --database-url $SERVICE_DB --concurrency 2' for Instance API")
    print("- Try pip install fastjob-pro for dashboard and advanced scheduling")


if __name__ == "__main__":
    asyncio.run(main())
