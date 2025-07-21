# FastJob

**Tired of the complexity of setting up Celery? FastJob is the Python job queue with a beautiful API that gets out of your way.**

FastJob is a background job library I built for developers who believe code should be elegant, not just functional. It uses PostgreSQL for rock-solid persistence and embraces Python's async/await syntax with APIs that make you smile while you write them.

After spending too many hours wrestling with Redis configurations, broker settings, and Celery's daunting documentation just to process some background tasks, I decided to build something better. FastJob is what I wish existed when I started building async Python applications - simple, type-safe, and actually enjoyable to use.

## Why I Built FastJob (And Why You'll Love It)
**Gorgeous APIs** - From `@fastjob.job()` to fluent scheduling, everything reads like natural language

**🎯 Type-Safe Jobs**: Use Pydantic models to define your job arguments. FastJob automatically validates incoming jobs, so you can be confident your data is correct - no more mysterious job failures from bad data.

**⚡ Truly Asynchronous**: Built from the ground up on asyncio and asyncpg. Perfect for I/O-bound tasks and modern web frameworks like FastAPI. Your jobs run efficiently without blocking.

**🏗️ Zero Infrastructure Headaches**: Uses PostgreSQL (which you already have) instead of requiring Redis, RabbitMQ, or other message brokers. One less thing to deploy, monitor, and maintain.

**🚀 Incredible DX**: Embedded worker for development means no additional processes to manage. Write jobs, enqueue them, see them run - all in your existing dev environment.

**📊 Production-Ready Monitoring**: Built-in job introspection, queue statistics, and CLI tools that actually help you understand what's happening in production.

## Installation

```bash
pip install fastjob
```

## 5-Minute Quickstart

Get FastJob running in under 5 minutes with this complete, copy-pasteable example:

### 1. Install and Setup Database
```bash
pip install fastjob
createdb fastjob_demo
export FASTJOB_DATABASE_URL="postgresql://localhost/fastjob_demo"
fastjob migrate
```

### 2. Define Your Jobs (`jobs.py`)
```python
import asyncio
import fastjob

@fastjob.job()
async def send_welcome_email(user_email: str, name: str):
    print(f"📧 Sending welcome email to {name} at {user_email}")
    await asyncio.sleep(1)  # Simulate email sending
    print(f"✅ Email sent successfully!")

@fastjob.job(retries=3, queue="payments")
async def process_payment(order_id: int, amount: float):
    print(f"💳 Processing ${amount} payment for order {order_id}")
    await asyncio.sleep(2)  # Simulate payment processing
    print(f"✅ Payment processed successfully!")
```

### 3. Enqueue Jobs (`main.py`)
```python
import asyncio
from jobs import send_welcome_email, process_payment
import fastjob

async def main():
    print("🚀 Enqueueing some jobs...")

    # Enqueue a welcome email
    job_id1 = await fastjob.enqueue(
        send_welcome_email,
        user_email="alice@example.com",
        name="Alice"
    )
    print(f"📝 Enqueued email job: {job_id1}")

    # Enqueue a payment job
    job_id2 = await fastjob.enqueue(
        process_payment,
        order_id=12345,
        amount=99.99
    )
    print(f"📝 Enqueued payment job: {job_id2}")

    print("✅ Jobs enqueued! Now start a worker to process them.")

if __name__ == "__main__":
    asyncio.run(main())
```

### 4. Run the Worker
```bash
# In one terminal - start the worker
fastjob worker

# In another terminal - enqueue the jobs
python main.py
```

**🎉 That's it!** You should see your jobs being processed in the worker terminal.

The jobs run asynchronously, get retried automatically if they fail, and you can monitor everything with `fastjob jobs list`.

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
fastjob worker --concurrency 4 --queues default,critical
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

## 🚀 What's Next?

FastJob is more than just a job queue. When you're ready to scale, check out what our premium tiers offer:

### FastJob Pro - For Growing Applications
Perfect for teams who need **recurring jobs**, **advanced scheduling**, and a **beautiful web dashboard**:

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

### FastJob Enterprise - For Production at Scale
When you need **enterprise-grade monitoring**, **webhooks**, and **production observability**:

- 📊 **Production Metrics**: Prometheus integration, custom dashboards, performance monitoring
- 🔔 **Smart Webhooks**: Get notified in Slack when jobs fail, integrate with your existing systems
- 📝 **Structured Logging**: Machine-parseable logs that work with your ELK stack, Datadog, etc.
- 🎯 **Dead Letter Management**: Advanced failure analysis and bulk retry operations
- 🔒 **Enterprise Security**: Audit logs, role-based access, compliance features

**Migration**: `pip install fastjob-enterprise` - still zero code changes required.

### 🏗️ Built on Solid Plugin Architecture

FastJob uses a professional plugin system that ensures:

- **Predictable imports**: `import fastjob` always works reliably
- **IDE-friendly**: Go to Definition, autocomplete, and type checking work perfectly
- **Independent evolution**: Free, Pro, and Enterprise packages can update independently
- **No technical debt**: Clean architecture that scales with your needs

```python
# Your code stays exactly the same:
import fastjob

@fastjob.job()
async def my_task():
    pass

# But you get new features automatically when you upgrade:
# Free: fastjob.enqueue()
# Pro: fastjob.every("5m").do() + fastjob.dashboard
# Enterprise: fastjob.get_system_metrics() + fastjob.setup_webhooks()
```

This isn't magic - it's careful engineering that makes upgrades feel seamless.

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
fastjob worker --concurrency 4
```

**🎯 Result**: Same `@fastjob.job()` functions, same `await fastjob.enqueue()` calls, different worker management. Perfect developer experience.

## 📁 Job Organization Made Simple

FastJob automatically discovers your jobs - no configuration needed for most projects:

### Zero-config approach (recommended)

Create a `jobs/` directory in your project root:

```
my-project/
├── main.py          # Your web app
├── jobs/            # ✅ FastJob finds this automatically
│   ├── __init__.py  # Empty file
│   ├── email.py     # Email-related jobs
│   ├── images.py    # Image processing jobs
│   └── reports.py   # Report generation jobs
└── requirements.txt
```

**jobs/email.py:**
```python
import fastjob

@fastjob.job(retries=3, queue="emails")
async def send_welcome_email(user_email: str, name: str):
    # Your email logic here
    pass

@fastjob.job(retries=2, queue="emails")
async def send_password_reset(user_id: int):
    # Your password reset logic
    pass
```

**jobs/images.py:**
```python
import fastjob

@fastjob.job(retries=1, queue="media")
async def resize_image(image_path: str, width: int, height: int):
    # Your image processing logic
    pass

@fastjob.job(queue="media")
async def generate_thumbnail(image_path: str):
    # Your thumbnail generation logic
    pass
```

**That's it!** FastJob finds and imports all jobs automatically when workers start.

### Custom job module (advanced)

If you prefer a different structure:

```bash
export FASTJOB_JOBS_MODULE="myapp.background_tasks"
```

FastJob will then look for jobs in `myapp/background_tasks/` instead.

### 🔍 How job discovery works

1. **FastJob looks for `FASTJOB_JOBS_MODULE`** (default: `"jobs"`)
2. **Falls back to `jobs/` directory** in your project root
3. **Imports all Python files** and registers `@fastjob.job()` functions
4. **Works with packages or individual files** - your choice

The beauty is that jobs are discovered automatically, so you can focus on writing them, not configuring them.

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