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

## The API You'll Actually Love

**FastJob feels like writing regular Python functions:**

```python
import fastjob

@fastjob.job()
async def send_welcome_email(user_email: str, name: str):
    # Your email logic here - this is just a regular async function
    print(f"📧 Sending welcome to {name} at {user_email}")
    # ... actual email sending logic

@fastjob.job(retries=3, queue="payments")
async def process_payment(order_id: int, amount: float):
    # Your payment logic here
    print(f"💳 Processing ${amount} for order {order_id}")
    # ... actual payment processing

# Enqueue jobs anywhere in your app
await fastjob.enqueue(send_welcome_email, 
                     user_email="alice@example.com", 
                     name="Alice")

await fastjob.enqueue(process_payment, 
                     order_id=12345, 
                     amount=99.99)
```

**That's it.** No complex configuration, no separate config files, no worker classes. Just decorated functions and simple enqueue calls.

## Two APIs: Start Simple, Scale When Needed

FastJob supports two usage patterns - **start with Global API for simplicity, migrate to Instance API when you need isolation**:

### 🎯 Global API (Most Apps)

Perfect for single applications with one database:

```python
import fastjob

# Simple global configuration
@fastjob.job()
async def send_email(to: str): pass

await fastjob.enqueue(send_email, to="user@example.com")
```

### 🏗️ Instance API (Microservices)

When you need separate databases per service:

```python
from fastjob import FastJob

# Each service gets its own instance and database
user_service = FastJob(database_url="postgresql://localhost/users")
billing_service = FastJob(database_url="postgresql://localhost/billing")

@user_service.job()
async def welcome_email(user_id: int): pass

@billing_service.job()
async def process_invoice(invoice_id: int): pass

# Each service processes its own jobs independently
await user_service.enqueue(welcome_email, user_id=123)
await billing_service.enqueue(process_invoice, invoice_id=456)
```

**When to use which:**
- **Global API**: Single app, one database (90% of use cases)
- **Instance API**: Microservices, multi-tenant apps, or when you need job isolation

## Quick Setup (30 seconds)

```bash
pip install fastjob
createdb your_app_db
export FASTJOB_DATABASE_URL="postgresql://localhost/your_app_db"
fastjob setup
```

Now your jobs run. Really.

## Development vs Production: Same Code, Different Worker Management

The beautiful thing about FastJob is your job code stays identical everywhere. Only the worker management changes:

### Development: Everything Just Works

```python
from fastapi import FastAPI
import fastjob

app = FastAPI()

@fastjob.job()
async def resize_uploaded_image(user_id: int, image_path: str):
    # Your image processing logic
    pass

@app.post("/upload-photo/")
async def upload_photo(user_id: int, image_data: bytes):
    image_path = save_image(image_data)
    
    # Enqueue the background job
    await fastjob.enqueue(resize_uploaded_image, 
                         user_id=user_id, 
                         image_path=image_path)
    
    return {"status": "uploaded", "processing": "queued"}

@app.on_event("startup")
async def startup():
    if fastjob.run_in_dev_mode():
        # Development: jobs run in your web server process
        fastjob.start_embedded_worker()
```

**Run your app:** `FASTJOB_DEV_MODE=true python -m uvicorn main:app`

Jobs process automatically in your web server. No separate processes, no Docker containers, no complexity.

### Production: Scale Jobs Independently

```bash
# Your app runs normally (same code!)
python -m uvicorn main:app

# Terminal 2: Run dedicated job workers
fastjob start --concurrency 4 --queues default,urgent
```

**Same `@fastjob.job()` functions, same `enqueue()` calls.** Just different worker management.

## Core Features That Just Work

### Type Safety (Finally!)

```python
from pydantic import BaseModel

class EmailJob(BaseModel):
    to: str
    subject: str
    user_id: int

@fastjob.job(args_model=EmailJob)
async def send_email(to: str, subject: str, user_id: int):
    # Arguments are validated before the job runs
    # No more mysterious failures from bad data
    pass
```

### Priority Queues

```python
@fastjob.job(priority=1, queue="critical")    # High priority
async def emergency_alert():
    pass

@fastjob.job(priority=100, queue="background") # Low priority  
async def cleanup_old_files():
    pass
```

### Job Scheduling

```python
from datetime import timedelta

# Run in 1 hour
await fastjob.schedule(send_reminder, 
                      run_in=timedelta(hours=1), 
                      user_id=123)

# Run at specific time
await fastjob.schedule(send_reminder, 
                      run_at=datetime(2025, 12, 25, 9, 0))
```

### Unique Jobs (No Duplicates)

```python
@fastjob.job(unique=True)
async def send_welcome_email(user_email: str):
    # Only one welcome email per user_email can be queued
    pass

# These return the same job ID (second one doesn't create duplicate)
job1 = await fastjob.enqueue(send_welcome_email, user_email="alice@example.com")
job2 = await fastjob.enqueue(send_welcome_email, user_email="alice@example.com")
assert job1 == job2
```

### Job Management

```python
# Check job status
status = await fastjob.get_job_status(job_id)

# Cancel jobs that haven't started
await fastjob.cancel_job(job_id)

# Retry failed jobs
await fastjob.retry_job(job_id)            

# List recent failures
failed_jobs = await fastjob.list_jobs(status="failed", limit=10)
```

## CLI That Actually Helps

**Global API** (uses your configured database):
```bash
# Setup database (run once)
fastjob setup

# Start workers (production)
fastjob start --concurrency 4 --queues default,urgent

# Check system health
fastjob status --verbose --jobs
```

**Instance API** (target specific databases):
```bash
# Setup specific service database
fastjob setup --database-url="postgresql://localhost/user_service"

# Start workers for specific service
fastjob start --database-url="postgresql://localhost/user_service" --concurrency 2

# Monitor specific service
fastjob status --database-url="postgresql://localhost/user_service"
```

That's it. Three commands that work with both APIs.

## Scaling Up: Pro and Enterprise

As your app grows, you can upgrade seamlessly:

**FastJob Pro** adds recurring jobs and a web dashboard:

```python
# Global API - recurring jobs (zero code changes needed)
fastjob.every("10m").do(cleanup_temp_files)
fastjob.schedule("0 9 * * 1-5").job(send_daily_report)

# Instance API - per-service recurring jobs
user_service.every("5m").do(cleanup_inactive_sessions)
billing_service.schedule("0 2 * * *").job(generate_invoices)
```

```bash
# Global API dashboard
fastjob dashboard  # http://localhost:6161

# Instance API - monitor each service separately
fastjob dashboard --database-url="postgresql://localhost/users" --port 6161
fastjob dashboard --database-url="postgresql://localhost/billing" --port 6162
```

**FastJob Enterprise** adds production monitoring:
- Performance metrics and alerting
- Webhook notifications (Slack, Teams, etc.)
- Structured logging for monitoring stacks
- Advanced failure analysis and dead letter queues

**Upgrading:** Just `pip install fastjob-pro` or `fastjob-enterprise` - your existing code doesn't change.

## Configuration (Optional)

FastJob works with minimal configuration:

```bash
# Required: Database connection (you probably already have this)
export FASTJOB_DATABASE_URL="postgresql://user:password@localhost/myapp"

# Optional: Development mode
export FASTJOB_DEV_MODE=true
```

Everything else has sensible defaults.

## Framework Integration Examples

### FastAPI (Perfect Match)

```python
from fastapi import FastAPI
import fastjob

app = FastAPI()

@fastjob.job()
async def process_upload(file_id: int):
    pass

@app.post("/upload/")
async def upload_file(file_id: int):
    await fastjob.enqueue(process_upload, file_id=file_id)
    return {"status": "processing"}

@app.on_event("startup")
async def startup():
    if fastjob.run_in_dev_mode():
        fastjob.start_embedded_worker()
```

### Django (Async Views)

```python
from django.http import JsonResponse
import fastjob

@fastjob.job()
async def send_notification(user_id: int):
    pass

async def trigger_notification(request):
    user_id = request.POST.get('user_id')
    await fastjob.enqueue(send_notification, user_id=int(user_id))
    return JsonResponse({"status": "queued"})
```

### Flask (With asyncio)

```python
from flask import Flask
import fastjob
import asyncio

app = Flask(__name__)

@fastjob.job()
async def background_task(data: str):
    pass

@app.route('/trigger')
def trigger():
    asyncio.run(fastjob.enqueue(background_task, data="test"))
    return {"status": "queued"}
```

## Migrating from Celery

**Replace this Celery complexity:**

```python
# Celery (complex)
from celery import Celery
app = Celery('myapp', broker='redis://localhost:6379/0')

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def send_email(self, user_email, subject):
    pass

# Separate worker process required
# celery -A myapp worker --loglevel=info
```

**With this FastJob simplicity:**

```python
# FastJob (simple)
import fastjob

@fastjob.job(retries=3)
async def send_email(user_email: str, subject: str):
    pass

# Development: embedded worker
fastjob.start_embedded_worker()

# Production: fastjob start
```

**Key improvements:**
- ✅ **No Redis/RabbitMQ** - uses your existing PostgreSQL
- ✅ **Embedded development mode** - no separate processes locally
- ✅ **Type safety** - Pydantic validation built-in
- ✅ **Modern async** - no sync/async complexity

## Production Deployment

### Systemd Service

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

### Multiple Queues

**Global API:**
```bash
# Dedicated workers for different job types
fastjob start --queues critical,emails --concurrency 2
fastjob start --queues background --concurrency 1
```

**Instance API:**
```bash
# Per-service queue management
fastjob start --database-url="postgresql://localhost/users" --queues user_emails,notifications --concurrency 2
fastjob start --database-url="postgresql://localhost/billing" --queues invoices,payments --concurrency 4
```

## Testing

```bash
pip install -e ".[dev]"
createdb fastjob_test
python -m pytest tests/ -v
```

## Why I Built This

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