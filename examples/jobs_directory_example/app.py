#!/usr/bin/env python3
"""
FastJob Jobs Directory Example

This example demonstrates the zero-configuration job discovery feature.
FastJob automatically finds and registers all jobs in the jobs/ directory.

Run this example:
1. Set your database URL: export FASTJOB_DATABASE_URL="postgresql://..."
2. Run: python app.py

Or test with workers:
1. Start worker: fastjob worker --concurrency 2
2. Run jobs: python app.py --worker-mode=external
"""

import asyncio
import sys
from datetime import datetime, timedelta

import fastjob


async def main():
    """Demonstrate jobs from the jobs/ directory."""
    print("🚀 FastJob Jobs Directory Example")
    print("=" * 50)

    # Check if we should use embedded worker or external
    use_embedded = "--worker-mode=external" not in sys.argv

    if use_embedded:
        print("Starting embedded worker (jobs will process automatically)...")
        fastjob.start_embedded_worker()
    else:
        print("Using external worker mode (start worker with: fastjob worker)")

    try:
        print("\n📧 Email Jobs")
        print("-" * 20)

        # Jobs from jobs/email.py are automatically available
        job_id = await fastjob.enqueue(
            "jobs.email.send_welcome_email",  # Full module path
            user_email="alice@example.com",
            name="Alice Smith",
        )
        print(f"   Enqueued welcome email: {job_id}")

        # Or use the function directly (after import)
        from jobs.email import send_password_reset_email

        job_id = await fastjob.enqueue(
            send_password_reset_email,
            user_email="bob@example.com",
            reset_token="abc123xyz",
        )
        print(f"   Enqueued password reset: {job_id}")

        print("\n🖼️  Image Processing Jobs")
        print("-" * 25)

        from jobs.images import resize_image, generate_thumbnails

        job_id = await fastjob.enqueue(
            resize_image, image_path="/uploads/photo.jpg", width=800, height=600
        )
        print(f"   Enqueued image resize: {job_id}")

        job_id = await fastjob.enqueue(
            generate_thumbnails,
            image_path="/uploads/photo.jpg",
            sizes=[(150, 150), (300, 300), (600, 400)],
        )
        print(f"   Enqueued thumbnail generation: {job_id}")

        print("\n📊 Report Generation Jobs")
        print("-" * 26)

        from jobs.reports import generate_daily_report

        job_id = await fastjob.enqueue(
            generate_daily_report, date=datetime.now().strftime("%Y-%m-%d")
        )
        print(f"   Enqueued daily report: {job_id}")

        # Schedule a report for tomorrow
        tomorrow = datetime.now() + timedelta(days=1)
        job_id = await fastjob.schedule_at(
            generate_daily_report,
            when=tomorrow.replace(hour=9, minute=0, second=0),
            date=tomorrow.strftime("%Y-%m-%d"),
        )
        print(f"   Scheduled tomorrow's report: {job_id}")

        print("\n💌 Newsletter Example (Multiple Subscribers)")
        print("-" * 43)

        from jobs.email import send_newsletter

        subscribers = ["user1@example.com", "user2@example.com", "user3@example.com"]
        job_id = await fastjob.enqueue(
            send_newsletter,
            subscriber_emails=subscribers,
            subject="FastJob Monthly Update",
        )
        print(f"   Enqueued newsletter: {job_id}")

        if use_embedded:
            print("\n⏳ Processing jobs (watch the output above)...")
            await asyncio.sleep(15)  # Give jobs time to complete

            print("\n📈 Job Statistics")
            print("-" * 16)

            stats = await fastjob.get_queue_stats()
            for queue_stat in stats:
                queue_name = queue_stat["queue"]
                total = queue_stat["total_jobs"]
                done = queue_stat["done"]
                print(f"   {queue_name}: {done}/{total} jobs completed")

        else:
            print("\n👀 Jobs enqueued! Start your worker to process them:")
            print("   fastjob worker --concurrency 2")

        print("\n✅ Example completed!")
        print("\n💡 Key takeaways:")
        print("   • No configuration needed - FastJob found jobs/ automatically")
        print("   • Different job types organized in separate files")
        print("   • Jobs can use priorities, retries, and custom queues")
        print("   • Mix of immediate and scheduled job execution")

    finally:
        if use_embedded:
            print("\nStopping embedded worker...")
            await fastjob.stop_embedded_worker()


if __name__ == "__main__":
    asyncio.run(main())
