#!/usr/bin/env python3
"""
FastJob Enhanced Features Demo

This example shows off the latest features that make job management much easier:
- Check job status and get detailed info about any job
- Cancel jobs that are taking too long or retry failed ones
- Prevent duplicate jobs from cluttering your queue
- Use powerful CLI commands to manage everything
- Get insights into how your queues are performing

Getting started:
1. First, set up your database: fastjob migrate
2. Run this demo: python enhanced_features_example.py
3. Then try these handy CLI commands:
   - fastjob status                 # See what's happening
   - fastjob jobs list              # Browse all jobs
   - fastjob jobs show <job_id>     # Dive into details
   - fastjob queues list            # Check queue health
"""

import asyncio
import time
from typing import Optional
from pydantic import BaseModel

import fastjob


# Job argument validation with Pydantic
class EmailArgs(BaseModel):
    to: str
    subject: str
    message: str
    priority: Optional[str] = "normal"


class ReportArgs(BaseModel):
    report_type: str
    start_date: str
    end_date: str


# A typical job for sending emails
@fastjob.job(retries=2, priority=50, queue="email")
def send_email(to: str, subject: str, message: str):
    """Sends an email notification (we'll just simulate it here)"""
    print(f"📧 Sending email to {to}: {subject}")
    time.sleep(1)  # Pretend we're doing some network work
    print(f"✅ Email sent to {to}")


# This job won't run twice with the same parameters - handy for reports!
@fastjob.job(retries=1, priority=10, queue="reports", unique=True, args_model=ReportArgs)
def generate_daily_report(report_type: str, start_date: str, end_date: str):
    """Creates a daily report, but only one per unique date range"""
    print(f"📊 Generating {report_type} report for {start_date} to {end_date}")
    time.sleep(2)  # Reports take a bit longer
    print(f"✅ Report {report_type} completed")


# Payment processing gets top priority
@fastjob.job(retries=3, priority=1, queue="urgent")
def process_payment(payment_id: str, amount: float):
    """Handle payment processing - this is important stuff!"""
    print(f"💳 Processing payment {payment_id} for ${amount}")
    time.sleep(0.5)  # Quick payment processing
    print(f"✅ Payment {payment_id} processed successfully")


# Sometimes things go wrong - this job helps us test error handling
@fastjob.job(retries=2, priority=100, queue="background")
def flaky_task(task_id: str, should_fail: bool = False):
    """A job that might fail - useful for testing retry logic"""
    print(f"🔄 Running flaky task {task_id}")
    
    if should_fail:
        raise Exception(f"Task {task_id} failed intentionally")
    
    time.sleep(1)
    print(f"✅ Task {task_id} completed successfully")


async def demonstrate_enhanced_features():
    """Demonstrate all the enhanced features"""
    
    print("🚀 FastJob Enhanced Features Demo")
    print("=" * 50)
    
    # 1. Enqueue various jobs
    print("\n1. Enqueueing jobs...")
    
    job1 = await fastjob.enqueue(send_email, 
        to="user@example.com", 
        subject="Welcome!", 
        message="Welcome to our service"
    )
    print(f"   📧 Email job queued: {job1}")
    
    job2 = await fastjob.enqueue(generate_daily_report,
        report_type="sales",
        start_date="2024-01-01", 
        end_date="2024-01-31"
    )
    print(f"   📊 Report job queued: {job2}")
    
    # Try to enqueue the same unique job - should return same ID
    job2_duplicate = await fastjob.enqueue(generate_daily_report,
        report_type="sales",
        start_date="2024-01-01", 
        end_date="2024-01-31"
    )
    print(f"   📊 Duplicate report job (should be same ID): {job2_duplicate}")
    print(f"   ✅ Unique job working: {job2 == job2_duplicate}")
    
    job3 = await fastjob.enqueue(process_payment,
        payment_id="PAY123",
        amount=99.99
    )
    print(f"   💳 Payment job queued: {job3}")
    
    job4 = await fastjob.enqueue(flaky_task,
        task_id="TASK001", 
        should_fail=False
    )
    print(f"   🔄 Flaky task queued: {job4}")
    
    # Enqueue a job that will fail
    job5 = await fastjob.enqueue(flaky_task,
        task_id="TASK002",
        should_fail=True
    )
    print(f"   💥 Failing task queued: {job5}")
    
    # 2. Demonstrate job introspection
    print("\n2. Job introspection...")
    
    # Get job status
    job_status = await fastjob.get_job_status(job1)
    if job_status:
        print(f"   📧 Email job status: {job_status['status']} (priority: {job_status['priority']})")
    
    # List all jobs
    all_jobs = await fastjob.list_jobs(limit=10)
    print(f"   📋 Total jobs in queue: {len(all_jobs)}")
    
    # List jobs by queue
    email_jobs = await fastjob.list_jobs(queue="email", limit=5)
    print(f"   📧 Email queue jobs: {len(email_jobs)}")
    
    # Get queue statistics
    queue_stats = await fastjob.get_queue_stats()
    print(f"   📊 Active queues: {len(queue_stats)}")
    for queue in queue_stats:
        print(f"      {queue['queue']}: {queue['total_jobs']} total, {queue['queued']} queued")
    
    # 3. Process some jobs
    print("\n3. Processing jobs...")
    
    # Start embedded worker to process jobs
    print("   🏃 Starting embedded worker...")
    worker_task = asyncio.create_task(
        fastjob.start_embedded_worker(concurrency=2, run_once=True)
    )
    
    # Wait for worker to finish
    await worker_task
    print("   ✅ Worker finished processing available jobs")
    
    # 4. Demonstrate job management
    print("\n4. Job management features...")
    
    # Check if any jobs failed
    failed_jobs = await fastjob.list_jobs(status="failed", limit=5)
    if failed_jobs:
        failed_job = failed_jobs[0]
        print(f"   💥 Found failed job: {failed_job['id']}")
        
        # Retry the failed job
        retry_success = await fastjob.retry_job(failed_job['id'])
        if retry_success:
            print(f"   🔄 Retried failed job: {failed_job['id']}")
        
        # Check updated status
        updated_status = await fastjob.get_job_status(failed_job['id'])
        if updated_status:
            print(f"   📊 Job status after retry: {updated_status['status']}")
    
    # Enqueue a job and then cancel it
    cancel_job = await fastjob.enqueue(flaky_task, task_id="CANCEL_ME", should_fail=False)
    print(f"   🎯 Job to cancel queued: {cancel_job}")
    
    cancel_success = await fastjob.cancel_job(cancel_job)
    if cancel_success:
        print(f"   ❌ Successfully cancelled job: {cancel_job}")
        
        # Verify cancellation
        cancelled_status = await fastjob.get_job_status(cancel_job)
        if cancelled_status:
            print(f"   📊 Cancelled job status: {cancelled_status['status']}")
    
    # 5. Final statistics
    print("\n5. Final statistics...")
    
    final_stats = await fastjob.get_queue_stats()
    total_processed = sum(q['done'] for q in final_stats)
    total_failed = sum(q['failed'] + q['dead_letter'] for q in final_stats)
    total_cancelled = sum(q['cancelled'] for q in final_stats)
    
    print(f"   ✅ Jobs completed: {total_processed}")
    print(f"   💥 Jobs failed: {total_failed}")
    print(f"   ❌ Jobs cancelled: {total_cancelled}")
    
    print("\n🎉 Demo completed!")
    print("\nTry these CLI commands:")
    print("  fastjob status                 # Show overall status")
    print("  fastjob jobs list              # List all jobs")
    print("  fastjob jobs list --failed     # List failed jobs") 
    print("  fastjob queues list            # Show queue statistics")
    print("  fastjob jobs show <job_id>     # Show job details")


async def main():
    """Main function"""
    try:
        await demonstrate_enhanced_features()
    except KeyboardInterrupt:
        print("\n👋 Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())