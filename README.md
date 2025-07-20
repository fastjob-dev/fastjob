# FastJob

**The job queue with the most beautiful API in Python**

FastJob is a background job library I built for developers who believe code should be elegant, not just functional. It uses PostgreSQL for rock-solid persistence and embraces Python's async/await syntax with APIs that make you smile while you write them.

## Why FastJob is Different

I was tired of job queues that felt like work to use. FastJob is different - every API is designed to be intuitive, powerful, and genuinely enjoyable:

- **Gorgeous APIs** - From `@fastjob.job()` to fluent scheduling, everything reads like natural language
- **Zero Infrastructure** - Uses PostgreSQL (which you already have) instead of Redis/RabbitMQ complexity
- **Async Native** - Built for modern Python 3.10+ with proper async/await throughout
- **Type Safe** - Pydantic integration keeps your jobs bulletproof
- **Incredible DX** - Embedded worker for development, production-ready CLI, job introspection that actually helps

## Installation

```bash
pip install fastjob
```

## Quick Start

### Set up your database

```bash
createdb my_app_jobs
export FASTJOB_DATABASE_URL="postgresql://user:password@localhost/my_app_jobs"
fastjob migrate
```

### The Most Beautiful Job Queue API You'll Ever Use

```python
import fastjob

# Define jobs with the simplest decorator imaginable
@fastjob.job()
async def send_welcome_email(user_email: str, name: str):
    print(f"Sending welcome email to {name} at {user_email}")
    # Your email logic here

@fastjob.job(retries=5, queue="critical")
async def process_payment(order_id: int, amount: float):
    print(f"Processing ${amount} for order {order_id}")
    # Your payment processing logic

# Enqueue jobs with natural, readable syntax
job_id = await fastjob.enqueue(
    send_welcome_email,
    user_email="alice@example.com",
    name="Alice"
)

# Priority jobs? Just as elegant
urgent_job = await fastjob.enqueue(
    process_payment,
    priority=1,  # Lower = higher priority
    order_id=12345,
    amount=99.99
)

# Schedule jobs for later with beautiful timing APIs
await fastjob.schedule_at(
    send_welcome_email,
    when=datetime(2025, 12, 25, 9, 0),  # Christmas morning
    user_email="santa@northpole.com",
    name="Santa"
)

await fastjob.schedule_in(
    process_payment,
    seconds=3600,  # One hour from now
    order_id=54321,
    amount=149.99
)
```

### The Development Experience You've Been Waiting For

**🎯 IMPORTANT: Your job code is identical between development and production** - only worker startup differs!

**Local Development (No Additional Processes):**
```python
# Add this to your FastAPI/Django/Flask app startup
fastjob.start_embedded_worker()

# That's it! Jobs now run in your web server process
# Same job definitions, same enqueuing code, same everything
```

**Production (Rock-Solid Worker Processes):**
```bash
# Your app runs normally (without embedded worker)
python -m uvicorn main:app

# Separate process runs the workers - same job code!
fastjob run-worker --concurrency 4 --queues default,critical
```

**🔑 Key Point**: Your `@fastjob.job()` functions and `await fastjob.enqueue()` calls are **exactly the same** in both environments. Only the worker startup changes.

## Real-world example: Same code, works everywhere

Here's how I use FastJob in a typical web app - **this exact code works in both development and production**:

```python
from fastapi import FastAPI
import fastjob
import os

app = FastAPI()

# ✅ These job definitions are IDENTICAL everywhere
@fastjob.job(retries=3)
async def resize_uploaded_image(user_id: int, image_path: str):
    # Resize image, upload to CDN, update database
    # This exact function works in development AND production
    pass

@fastjob.job(queue="emails", retries=2)
async def send_notification(user_id: int, message: str):
    # Send push notification or email
    # This exact function works in development AND production
    pass

# ✅ This API endpoint is IDENTICAL everywhere
@app.post("/upload-photo/")
async def upload_photo(user_id: int, image_data: bytes):
    # Save the raw image
    image_path = save_image(image_data)

    # This enqueuing code is IDENTICAL in development and production
    await fastjob.enqueue(resize_uploaded_image, user_id=user_id, image_path=image_path)

    return {"status": "uploaded", "processing": "queued"}

# 🔄 Only this startup code differs based on environment
@app.on_event("startup")
async def startup():
    if os.getenv("ENVIRONMENT") == "development":
        fastjob.start_embedded_worker()  # Development: embedded worker
    # Production: external workers handle jobs automatically

@app.on_event("shutdown")
async def shutdown():
    if os.getenv("ENVIRONMENT") == "development":
        await fastjob.stop_embedded_worker()
```

**Development deployment:**
```bash
export ENVIRONMENT=development
python -m uvicorn main:app --reload  # Worker runs inside your app
```

**Production deployment:**
```bash
export ENVIRONMENT=production
python -m uvicorn main:app           # App runs normally
fastjob run-worker --concurrency 4   # Workers run separately
```

**🎯 The key insight**: Your business logic never changes. Only worker management differs.

## Advanced features

### Type validation with Pydantic

```python
from pydantic import BaseModel

class EmailJobArgs(BaseModel):
    to: str
    subject: str
    body: str
    user_id: int

@fastjob.job(args_model=EmailJobArgs)
async def send_email(to: str, subject: str, body: str, user_id: int):
    # FastJob validates arguments before running
    pass
```

### Priority queues

```python
# Critical jobs get processed first
@fastjob.job(priority=1, queue="critical")
async def emergency_alert():
    pass

# Background cleanup can wait
@fastjob.job(priority=100, queue="maintenance")
async def cleanup_old_files():
    pass
```

### Scheduling jobs

```python
from datetime import datetime, timedelta

# Schedule for later
await fastjob.schedule_at(
    send_reminder,
    when=datetime.now() + timedelta(hours=24),
    user_id=123
)

# Schedule in X seconds
await fastjob.schedule_in(
    send_reminder,
    seconds=86400,  # 24 hours
    user_id=123
)
```

### Job introspection that actually helps

```python
# Check on your jobs like a pro
status = await fastjob.get_job_status(job_id)
print(f"Job {job_id} is {status}")

# Cancel jobs that haven't started yet
cancelled = await fastjob.cancel_job(job_id)

# Retry failed jobs
retried = await fastjob.retry_job(job_id)

# Get job insights
jobs = await fastjob.list_jobs(status="failed", limit=10)
stats = await fastjob.get_queue_stats()
```

## 🚀 Ready for More? Upgrade to FastJob Pro

The free version handles 90% of use cases beautifully. But when you need **recurring jobs**, **advanced scheduling**, and a **web dashboard**, FastJob Pro takes the same elegant APIs to the next level:

```python
# Recurring jobs with the same beautiful API
import fastjob  # Same import - zero code changes needed!

# Cron-style scheduling that feels natural
fastjob.schedule("*/15 * * * *").job(check_system_health)
fastjob.schedule("0 9 * * 1-5").job(send_daily_report)

# Human-readable scheduling
fastjob.every("10m").do(cleanup_temp_files)
fastjob.every("1h").do(process_analytics)

# Fluent advanced scheduling
await fastjob.schedule_job(generate_report)\
    .next_monday()\
    .at_time("09:00")\
    .with_priority(1)\
    .enqueue(report_type="weekly")

# Start the scheduler (one line!)
await fastjob.start_recurring_scheduler()

# Built-in dashboard
fastjob dashboard  # Opens at http://localhost:6161
```

**Migration from Free to Pro**: Literally just `pip install fastjob-pro` and you're done. Zero code changes required.

Learn more at [FastJob Pro](https://github.com/abhinavs/fastjob-pro)

## Configuration

FastJob is configured via environment variables:

```bash
# Required: Database connection
export FASTJOB_DATABASE_URL="postgresql://user:password@localhost/myapp"

# Optional: Where to find your job functions
export FASTJOB_JOBS_MODULE="myapp.jobs"

# Optional: Logging level
export FASTJOB_LOG_LEVEL="INFO"

# Optional: Environment detection for automatic worker management
export ENVIRONMENT="development"  # or "production"
```

### 🔄 Development vs Production: Same Code, Different Workers

**The most important thing to understand**: Your application code is **identical** between environments.

**Development Configuration:**
```bash
# .env.development
ENVIRONMENT=development
FASTJOB_DATABASE_URL="postgresql://localhost/myapp_dev"

# Your app automatically starts embedded worker
python -m uvicorn main:app --reload
```

**Production Configuration:**
```bash
# .env.production
ENVIRONMENT=production
FASTJOB_DATABASE_URL="postgresql://user:pass@prod-db/myapp"

# Your app runs normally
python -m uvicorn main:app

# Workers run separately
fastjob run-worker --concurrency 4
```

**🎯 Result**: Same `@fastjob.job()` functions, same `await fastjob.enqueue()` calls, different worker management. Perfect developer experience.

## Production deployment

### Systemd service

```ini
[Unit]
Description=FastJob Worker
After=postgresql.service

[Service]
Type=simple
User=myapp
WorkingDirectory=/path/to/myapp
Environment=FASTJOB_DATABASE_URL=postgresql://...
ExecStart=/path/to/venv/bin/fastjob run-worker --concurrency 4
Restart=always

[Install]
WantedBy=multi-user.target
```

### Docker

```dockerfile
FROM python:3.11
COPY . /app
WORKDIR /app
RUN pip install .
CMD ["fastjob", "run-worker", "--concurrency", "4"]
```

### Multiple queues

```bash
# Dedicated workers for different job types
fastjob run-worker --queues critical,emails --concurrency 2
fastjob run-worker --queues background --concurrency 1
```

## Testing

```bash
pip install -e ".[dev]"
createdb fastjob_test
python -m pytest tests/ -v
```

## Upgrading to Pro/Enterprise

I've built additional packages for teams that need more:

**FastJob Pro** adds:
- Web dashboard for monitoring jobs
- Recurring jobs (cron-style scheduling)
- Advanced scheduling features

**FastJob Enterprise** adds:
- Metrics and performance monitoring
- Structured logging
- Webhook notifications
- Dead letter queue management

Contact me at abhinav@apiclabs.com for commercial licensing.

## Why I built this

I've worked with background jobs in production for years and got frustrated with the complexity of existing solutions. Redis-based queues are fast but can lose jobs. Database-backed queues are reliable but often have clunky APIs.

FastJob combines the reliability of PostgreSQL with a clean, modern Python API. It's what I wish existed when I started building async Python applications.

## Contributing

Found a bug? Have an idea? I'd love to hear from you:

- **Issues**: GitHub Issues for bugs and feature requests
- **Email**: abhinav@apiclabs.com for questions
- **Twitter**: [@abhinav](https://twitter.com/abhinav)

## License

MIT - use it however you want.

---

**FastJob** - Background jobs that just work.

Built by [Abhinav Saxena](https://github.com/abhinavs)