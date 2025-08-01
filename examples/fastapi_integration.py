"""
FastAPI Integration Example with FastJob
Demonstrates how to integrate FastJob with a FastAPI web application.
"""

from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import fastjob


# Pydantic models for API
class EmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    priority: int = 100


class JobResponse(BaseModel):
    job_id: str
    message: str


class ProcessingRequest(BaseModel):
    data: List[str]
    priority: Optional[int] = 100


# Job definitions
@fastjob.job(retries=3)
async def send_notification_email(to: str, subject: str, body: str) -> dict:
    """Send notification email job."""
    print(f"📧 Sending email to {to}")
    print(f"Subject: {subject}")

    # Simulate email sending delay
    import asyncio

    await asyncio.sleep(1)

    # In real implementation, use email service like SendGrid, SES, etc.
    print(f"✅ Email sent successfully to {to}")

    return {"status": "sent", "to": to, "sent_at": datetime.now().isoformat()}


@fastjob.job(priority=50, queue="processing")
async def process_user_data(user_id: int, data: List[str]) -> dict:
    """Process user data job."""
    print(f"🔄 Processing data for user {user_id}")

    processed_items = []
    import asyncio

    for item in data:
        # Simulate processing
        await asyncio.sleep(0.2)
        processed_item = f"processed_{item}_{datetime.now().timestamp()}"
        processed_items.append(processed_item)
        print(f"  ✓ Processed: {item}")

    result = {
        "user_id": user_id,
        "processed_count": len(processed_items),
        "processed_items": processed_items,
        "completed_at": datetime.now().isoformat(),
    }

    print(f"✅ Processing completed for user {user_id}")
    return result


@fastjob.job(queue="reports")
async def generate_user_report(user_id: int, report_type: str) -> dict:
    """Generate user report job."""
    print(f"📊 Generating {report_type} report for user {user_id}")

    # Simulate report generation
    import asyncio

    await asyncio.sleep(2)

    report = {
        "user_id": user_id,
        "report_type": report_type,
        "generated_at": datetime.now().isoformat(),
        "data": {
            "total_actions": 42,
            "last_login": "2025-01-19T10:30:00",
            "status": "active",
        },
    }

    print(f"✅ Report generated for user {user_id}")
    return report


# FastAPI application
app = FastAPI(
    title="FastJob + FastAPI Example",
    description="Example web application using FastJob for background tasks",
    version="1.0.0",
)


@app.on_event("startup")
async def startup_event():
    """Start FastJob embedded worker in development mode."""
    if fastjob.is_dev_mode():
        print("🚀 Starting FastJob embedded worker (dev mode)...")
        fastjob.start_embedded_worker()
    else:
        print("📊 Production mode - workers run separately")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop FastJob embedded worker if running."""
    if fastjob.is_dev_mode():
        print("🛑 Stopping FastJob embedded worker...")
        await fastjob.stop_embedded_worker()


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "message": "FastJob + FastAPI Example",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/send-email", response_model=JobResponse)
async def send_email_endpoint(email_request: EmailRequest):
    """
    Send an email asynchronously using FastJob.

    The email will be processed in the background, allowing the API
    to respond immediately without waiting for the email to be sent.
    """
    try:
        job_id = await fastjob.enqueue(
            send_notification_email,
            to=email_request.to,
            subject=email_request.subject,
            body=email_request.body,
            priority=email_request.priority,
        )

        return JobResponse(
            job_id=job_id, message=f"Email queued successfully. Job ID: {job_id}"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue email: {str(e)}")


@app.post("/process-data/{user_id}", response_model=JobResponse)
async def process_data_endpoint(user_id: int, request: ProcessingRequest):
    """
    Process user data asynchronously.

    Large data processing tasks are handled in the background
    to avoid blocking the API response.
    """
    try:
        job_id = await fastjob.enqueue(
            process_user_data,
            user_id=user_id,
            data=request.data,
            priority=request.priority,
        )

        return JobResponse(
            job_id=job_id,
            message=f"Data processing queued for user {user_id}. Job ID: {job_id}",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to queue processing: {str(e)}"
        )


@app.post("/generate-report/{user_id}", response_model=JobResponse)
async def generate_report_endpoint(user_id: int, report_type: str = "summary"):
    """
    Generate a user report asynchronously.

    Report generation can be time-consuming, so it's handled
    in the background while the API responds immediately.
    """
    try:
        job_id = await fastjob.enqueue(
            generate_user_report,
            user_id=user_id,
            report_type=report_type,
            queue="reports",  # Use specific queue for reports
        )

        return JobResponse(
            job_id=job_id,
            message=f"Report generation queued for user {user_id}. Job ID: {job_id}",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue report: {str(e)}")


@app.post("/bulk-email", response_model=dict)
async def bulk_email_endpoint(emails: List[EmailRequest]):
    """
    Send multiple emails asynchronously.

    Demonstrates enqueueing multiple jobs efficiently.
    """
    job_ids = []

    try:
        for email in emails:
            job_id = await fastjob.enqueue(
                send_notification_email,
                to=email.to,
                subject=email.subject,
                body=email.body,
                priority=email.priority,
            )
            job_ids.append(job_id)

        return {
            "message": f"Queued {len(emails)} emails successfully",
            "job_ids": job_ids,
            "total_jobs": len(job_ids),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue emails: {str(e)}")


# Example of using FastAPI background tasks alongside FastJob
@app.post("/quick-task/{task_id}")
async def quick_task_endpoint(task_id: int, background_tasks: BackgroundTasks):
    """
    Example combining FastAPI BackgroundTasks with FastJob.

    Use FastAPI BackgroundTasks for very quick operations,
    FastJob for more complex or reliable background processing.
    """

    # Quick task using FastAPI's BackgroundTasks
    def quick_log():
        print(f"📝 Quick log for task {task_id}")

    background_tasks.add_task(quick_log)

    # Complex task using FastJob
    job_id = await fastjob.enqueue(
        process_user_data, user_id=task_id, data=[f"item_{i}" for i in range(5)]
    )

    return {
        "message": "Task queued",
        "task_id": task_id,
        "fastjob_id": job_id,
        "note": "Quick operation runs immediately, complex processing queued with FastJob",
    }


if __name__ == "__main__":
    import uvicorn

    print("🚀 Starting FastAPI + FastJob Example")
    print("📖 Visit http://localhost:8000/docs for interactive API documentation")
    print("\n💡 Example API calls:")
    print("  POST /send-email")
    print("  POST /process-data/123")
    print("  POST /generate-report/456")
    print("  POST /bulk-email")

    # For development only - use proper ASGI server in production
    uvicorn.run("fastapi_integration:app", host="0.0.0.0", port=8000, reload=True)
