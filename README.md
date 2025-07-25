# FastJob

**Because your background jobs shouldn't be a background worry.**

After spending too many hours wrestling with Celery's daunting documentation and the operational overhead of Redis just to run a simple background task, I decided to build the tool I wished I had.

I built FastJob on a simple, powerful idea: your database (PostgreSQL) is already rock-solid, so you shouldn't need another service just to enqueue jobs. It's a library that values developer happiness and elegant design over endless configuration, with a beautiful, type-safe API that feels like a joy to use, not a chore.

It's the job queue for developers who believe simple is beautiful.

## FastJob vs The Competition

| Feature              | Celery                    | RQ                      | FastJob                    |
| -------------------- | ------------------------- | ----------------------- | -------------------------- |
| **Setup Complexity** | Redis/RabbitMQ required   | Redis required          | ✅ Uses your PostgreSQL    |
| **Development**      | Separate worker process   | Separate worker process | ✅ Embedded in your app    |
| **Type Safety**      | Manual validation         | Manual validation       | ✅ Automatic with Pydantic |
| **Async Support**    | Limited/clunky            | None (sync only)        | ✅ Native asyncio          |
| **Web Dashboard**    | Flower (separate install) | Basic (separate)        | ✅ Built-in (Pro)          |
| **Job Scheduling**   | Celery Beat (complex)     | External cron needed    | ✅ Built-in (Pro)          |
| **Learning Curve**   | Steep                     | Moderate                | ✅ Gentle                  |

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
fastjob setup
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
fastjob start

# In another terminal - enqueue the jobs
python main.py
```

**🎉 That's it!** You should see your jobs being processed in the worker terminal.

The jobs run asynchronously, get retried automatically if they fail, and you can monitor everything with `fastjob status`.

### Development vs Production: Same Code, Different Setup

The best part? Your job code stays identical between development and production.

**Development:** Jobs run in your web server process (no extra setup needed)

```python
# Add to your app startup
fastjob.start_embedded_worker()
```

**Production:** Jobs run in separate worker processes (better for scale)

```bash
fastjob start --concurrency 4 --queues default,urgent
```

Same `@fastjob.job()` functions, same `enqueue()` calls. Just different worker management.

## A practical example

Here's a typical FastAPI app using FastJob:

```python
from fastapi import FastAPI
import fastjob

app = FastAPI()

@fastjob.job(retries=3)
async def resize_uploaded_image(user_id: int, image_path: str):
    # Your actual image processing logic here
    pass

@app.post("/upload-photo/")
async def upload_photo(user_id: int, image_data: bytes):
    image_path = save_image(image_data)

    # Enqueue the background job
    await fastjob.enqueue(resize_uploaded_image, user_id=user_id, image_path=image_path)

    return {"status": "uploaded", "processing": "queued"}

@app.on_event("startup")
async def startup():
    if fastjob.is_dev_mode():
        fastjob.start_embedded_worker()
```

**Development:** `FASTJOB_DEV_MODE=true python -m uvicorn main:app`
**Production:** `python -m uvicorn main:app` + `fastjob start`

Same code, different worker setup.

## More features

**Type validation:** Use Pydantic models to validate job arguments automatically

```python
class EmailJobArgs(BaseModel):
    to: str
    subject: str
    user_id: int

@fastjob.job(args_model=EmailJobArgs)
async def send_email(to: str, subject: str, user_id: int):
    # Arguments are validated before the job runs
    pass
```

**Priority queues:** Important jobs get processed first

```python
@fastjob.job(priority=1, queue="critical")    # High priority
async def emergency_alert():
    pass

@fastjob.job(priority=100, queue="background") # Low priority
async def cleanup_old_files():
    pass
```

**Unique jobs:** Prevent duplicate jobs from being queued

```python
@fastjob.job(unique=True)
async def send_welcome_email(user_email: str):
    # Only one welcome email per user_email can be queued at a time
    pass

# These will return the same job ID (second one won't create a new job)
job1 = await fastjob.enqueue(send_welcome_email, user_email="alice@example.com")
job2 = await fastjob.enqueue(send_welcome_email, user_email="alice@example.com")
assert job1 == job2

# Override uniqueness per enqueue
await fastjob.enqueue(regular_job, unique=True, data="prevent_duplicates")
```

**Job scheduling:** Run jobs later

```python
from datetime import timedelta

# Run in 1 hour
await fastjob.schedule(send_reminder, run_in=timedelta(hours=1), user_id=123)

# Run at specific time
await fastjob.schedule(send_reminder, run_at=datetime(2025, 12, 25, 9, 0))
```

**Job management:** Check on your jobs

```python
status = await fastjob.get_job_status(job_id)
await fastjob.cancel_job(job_id)           # Cancel if not started
await fastjob.retry_job(job_id)            # Retry failed job
jobs = await fastjob.list_jobs(status="failed", limit=10)
```

## Need more?

As your app grows, you might need additional features:

**FastJob Pro** adds recurring jobs and a web dashboard:

```python
# Recurring jobs (same API, no code changes)
fastjob.every("10m").do(cleanup_temp_files)
fastjob.schedule("0 9 * * 1-5").job(send_daily_report)

# Web dashboard (Pro)
fastjob status --verbose  # CLI status or use Pro web dashboard
```

**FastJob Enterprise** adds production monitoring:

- Performance metrics and alerting
- Webhook notifications (Slack, etc.)
- Structured logging for your monitoring stack
- Advanced failure analysis

**Upgrading:** Just `pip install fastjob-pro` or `fastjob-enterprise` - your existing code doesn't change.

Contact me at abhinav@apiclabs.com for Pro/Enterprise licensing.

## CLI Commands

FastJob provides 3 simple commands for all operations:

```bash
# Setup database (run once)
fastjob setup

# Start worker process
fastjob start --concurrency 4 --queues default,urgent

# Check system status
fastjob status --verbose --jobs
```

**Command details:**

- **`fastjob setup`** - Initialize/update database schema (replaces migrations)
- **`fastjob start`** - Start worker to process jobs (replaces worker command)
- **`fastjob status`** - Show system health, job stats, and queue info (replaces health/jobs/queues)

## Configuration

FastJob is configured via environment variables:

```bash
# Required: Database connection
export FASTJOB_DATABASE_URL="postgresql://user:password@localhost/myapp"

# Optional: Job result time-to-live in seconds (default: 300 = 5 minutes)
export FASTJOB_RESULT_TTL=300  # 300 = 5 minutes (default), 0 = delete immediately, 3600 = keep 1 hour

# Optional: Where to find your job functions
export FASTJOB_JOBS_MODULE="myapp.jobs"

# Optional: Logging level
export FASTJOB_LOG_LEVEL="INFO"

# Optional: Environment detection for automatic worker management
export FASTJOB_DEV_MODE=true
```

### Job cleanup

By default, successful jobs are kept for 5 minutes to allow for debugging and monitoring, then automatically cleaned up. Failed jobs are always kept for debugging.

```bash
# Delete immediately for high-volume production
export FASTJOB_RESULT_TTL=0  # Delete immediately

# Keep longer for debugging/auditing
export FASTJOB_RESULT_TTL=3600   # 1 hour
export FASTJOB_RESULT_TTL=86400  # 1 day
```

When TTL > 0, workers automatically clean up expired jobs every 5 minutes.

## Job organization

FastJob automatically finds your jobs. Just create a `jobs/` folder:

```
my-project/
├── main.py
├── jobs/
│   ├── __init__.py
│   ├── email.py     # Email jobs
│   └── images.py    # Image processing jobs
```

**jobs/email.py:**

```python
import fastjob

@fastjob.job(retries=3)
async def send_welcome_email(user_email: str, name: str):
    # Your email logic
    pass
```

FastJob finds and registers all `@fastjob.job()` functions automatically.

**Custom location:** Set `FASTJOB_JOBS_MODULE="myapp.tasks"` to use a different folder.

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
ExecStart=/path/to/venv/bin/fastjob start --concurrency 4
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
CMD ["fastjob", "start", "--concurrency", "4"]
```

### Multiple queues

```bash
# Dedicated workers for different job types
fastjob start --queues critical,emails --concurrency 2
fastjob start --queues background --concurrency 1
```

## Migrating from other job queues

### From Celery

**Replace this Celery setup:**

```python
# Celery setup (complex)
from celery import Celery
app = Celery('myapp', broker='redis://localhost:6379/0')

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def send_email(self, user_email, subject):
    # Your logic here
    pass

# Separate worker process required
# celery -A myapp worker --loglevel=info
```

**With this FastJob equivalent:**

```python
# FastJob (simple)
import fastjob

@fastjob.job(retries=3)
async def send_email(user_email: str, subject: str):
    # Same logic, but with type safety
    pass

# Development: embedded worker
fastjob.start_embedded_worker()

# Production: fastjob start
```

**Key differences:**

- ✅ **No Redis/RabbitMQ** - uses your existing PostgreSQL
- ✅ **Embedded development mode** - no separate worker process needed locally
- ✅ **Type safety** - Pydantic validation built-in
- ✅ **Modern async** - no sync/async complexity

### From RQ

**Replace this RQ setup:**

```python
# RQ (sync only)
from rq import Queue
from redis import Redis
redis_conn = Redis()
q = Queue(connection=redis_conn)

def process_data(data):
    # Sync function only
    pass

job = q.enqueue(process_data, data)
```

**With FastJob:**

```python
# FastJob (async-first)
import fastjob

@fastjob.job()
async def process_data(data: dict):
    # Async with type validation
    pass

await fastjob.enqueue(process_data, data={"key": "value"})
```

**Migration benefits:**

- ✅ **Async support** - RQ is sync-only, FastJob is async-first
- ✅ **No Redis dependency** - one less service to manage
- ✅ **Better development experience** - embedded worker for local dev

## Framework integration examples

### FastAPI (recommended)

```python
from fastapi import FastAPI
import fastjob

app = FastAPI()

@fastjob.job()
async def process_upload(file_id: int):
    # Process file in background
    pass

@app.post("/upload/")
async def upload_file(file_id: int):
    await fastjob.enqueue(process_upload, file_id=file_id)
    return {"status": "processing"}

@app.on_event("startup")
async def startup():
    if fastjob.is_dev_mode():
        fastjob.start_embedded_worker()
```

### Django

```python
# In Django, use async views with FastJob
from django.http import JsonResponse
import fastjob

@fastjob.job()
async def send_notification(user_id: int):
    # Send notification logic
    pass

async def trigger_notification(request):
    user_id = request.POST.get('user_id')
    await fastjob.enqueue(send_notification, user_id=int(user_id))
    return JsonResponse({"status": "queued"})
```

### Flask

```python
from flask import Flask
import fastjob
import asyncio

app = Flask(__name__)

@fastjob.job()
async def background_task(data: str):
    # Your async background task
    pass

@app.route('/trigger')
def trigger():
    # Use asyncio.run for sync Flask integration
    asyncio.run(fastjob.enqueue(background_task, data="test"))
    return {"status": "queued"}
```

## Testing

```bash
pip install -e ".[dev]"
createdb fastjob_test
python -m pytest tests/ -v
```

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
