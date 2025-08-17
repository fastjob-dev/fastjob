# FastJob

**The Python Job Queue Built for Developer Happiness**

Write once, run anywhere. Your FastJob code works identically in development and production – just with different worker deployment. No Redis complexity, no infrastructure headaches, just PostgreSQL and exceptional developer experience.

If you've worked with background jobs in Python, you know the drill: install Redis, configure Celery, set up separate worker processes, debug sync/async compatibility issues, and hope your jobs don't disappear when something goes wrong.

I built FastJob with a different philosophy: your PostgreSQL database is already handling your app's most critical data reliably – why not use it for jobs too? FastJob prioritizes developer productivity and simplicity over enterprise feature checklists.

It's the job queue for developers who believe **simple is beautiful**.

## FastJob vs Established Solutions

| Aspect               | Celery                    | RQ                     | FastJob                    |
| -------------------- | ------------------------- | ---------------------- | -------------------------- |
| **Infrastructure**   | Redis/RabbitMQ required   | Redis required         | ✅ Uses your PostgreSQL    |
| **Development**      | Separate worker process   | Separate process       | ✅ Embedded in your app    |
| **Type Safety**      | Manual validation         | Manual validation      | ✅ Automatic with Pydantic |
| **Async Support**    | Requires compatibility layer | Sync-only design     | ✅ Native asyncio          |
| **Microservices**    | Shared queue coordination | Manual queue separation | ✅ Database per service    |
| **Multi-Tenant**     | Custom isolation logic   | Limited support        | ✅ Database per tenant     |
| **Monitoring**       | Flower (separate service) | Basic CLI tools        | ✅ Built-in dashboard (Pro) |
| **Scheduling**       | Celery Beat (additional component) | External cron needed | ✅ In-code definitions (Pro) |
| **Getting Started**  | Significant setup time    | Moderate setup         | ✅ Minutes to first job    |

## The API You'll Actually Enjoy Using

Stop wrestling with worker classes and broker URLs. FastJob feels like writing normal Python:

```python
import fastjob

@fastjob.job()
async def send_welcome_email(user_email: str, name: str):
    # Just a regular async function - nothing special
    print(f"📧 Welcome {name}!")
    # Your email logic here...

@fastjob.job(retries=3, queue="payments")
async def process_payment(order_id: int, amount: float):
    # Type hints = automatic validation
    print(f"💳 Processing ${amount} for order {order_id}")
    # Your payment logic here...

# Enqueue anywhere in your app - it's just a function call
await fastjob.enqueue(send_welcome_email,
                     user_email="alice@example.com",
                     name="Alice")

await fastjob.enqueue(process_payment,
                     order_id=12345,
                     amount=99.99)
```

That's it. No worker classes. No broker configuration. No YAML files. Just decorated functions and clean enqueue calls.

## Quick Start

**The DX Magic:** Same code adapts automatically to development and production environments.

**Prerequisites:** PostgreSQL (most developers already have this)

```bash
pip install fastjob
```

Create `demo.py`:
```python
import asyncio
import fastjob

# Same configuration everywhere - environment controls behavior
fastjob.configure(
    database_url="postgresql://localhost/your_existing_db"
)

@fastjob.job()
async def send_email(email: str, name: str):
    print(f"📧 Sending to {name} at {email}")
    await asyncio.sleep(1)  # Simulate work
    print(f"✅ Sent!")

async def main():
    # ✨ The DX Magic: Same code adapts to any environment
    if fastjob.is_dev_mode():
        fastjob.start_embedded_worker()
        print("🔄 Dev mode: Jobs process instantly in your app")
    
    await fastjob.enqueue(send_email, email="alice@example.com", name="Alice")
    await asyncio.sleep(3)  # Watch it work

if __name__ == "__main__":
    asyncio.run(main())
```

**Development (embedded worker):**
```bash
export FASTJOB_DEV_MODE=true
python demo.py
```

**Production (separate workers):**
```bash
# Your app runs normally (no FASTJOB_DEV_MODE)
python demo.py

# Separate terminal: dedicated workers
fastjob worker --concurrency=4
```

**🚀 Write once, run anywhere** - environment variables control worker behavior, your code stays the same.

## What You Get

### ✅ **Zero Infrastructure Headaches**
```python
# No Redis to install, no message broker to configure
fastjob.configure(database_url="postgresql://localhost/myapp")
```

### ✅ **Developer Experience That Actually Works**
```python
# Safe for production - only runs embedded worker in development
if fastjob.is_dev_mode():
    fastjob.start_embedded_worker()
    
await fastjob.enqueue(my_job, data="test")
# Dev: Job runs immediately in the same process
# Prod: Job queues for external workers - same code, zero config changes
```

### ✅ **Type Safety That Prevents Bugs**
```python
@fastjob.job()
async def process_order(order_id: int, amount: float):
    # FastJob validates types automatically
    pass

# This raises a validation error before reaching your worker
await fastjob.enqueue(process_order, order_id="invalid", amount="not_a_number")
```

### ✅ **Microservices Without Shared Infrastructure**
```python
# Each service gets its own job database
user_service = FastJob(database_url="postgresql://localhost/users")
billing_service = FastJob(database_url="postgresql://localhost/billing")

# No more cross-service job contamination
```

## Production Setup

When you're ready for production, FastJob's simplicity really shines:

```bash
# 1. Configure your database (you already have one)
export FASTJOB_DATABASE_URL="postgresql://prod.db/myapp"

# 2. Run migrations (once)
fastjob migrate

# 3. Start workers (scale as needed)
fastjob worker --concurrency=8
```

**That's your entire production setup.** No Redis cluster, no RabbitMQ management, no additional monitoring.

### Framework Integration

FastJob works with whatever you're building:

```python
# FastAPI
@app.post("/users")
async def create_user(user_data: dict):
    await fastjob.enqueue(send_welcome_email, user_data)

# Django
def user_signup(request):
    asyncio.run(fastjob.enqueue(send_welcome_email, request.POST))

# Flask
@app.route("/users", methods=["POST"])
def create_user():
    asyncio.run(fastjob.enqueue(send_welcome_email, request.json))
```

## Two APIs: Choose Your Style

### Global API (Most Apps)
```python
import fastjob

@fastjob.job()
async def send_email(to: str, subject: str):
    pass

await fastjob.enqueue(send_email, to="user@example.com", subject="Welcome!")
```

### Instance API (Microservices)
```python
from fastjob import FastJob

user_service = FastJob(database_url="postgresql://localhost/users")
billing_service = FastJob(database_url="postgresql://localhost/billing")

@user_service.job()
async def send_welcome_email(user_id: int):
    pass

await user_service.enqueue(send_welcome_email, user_id=123)
```

**Perfect for:** Microservices, multi-tenant SaaS, team separation

## Features That Actually Matter

### Type Safety (Finally)

```python
from pydantic import BaseModel

class EmailArgs(BaseModel):
    to: str
    subject: str
    user_id: int

@fastjob.job(args_model=EmailArgs)
async def send_email(to: str, subject: str, user_id: int):
    # Arguments validated before job runs
    # No more mysterious "KeyError: 'user_id'" failures
    pass
```

### Priority Queues

```python
@fastjob.job(priority=1, queue="critical")    # Urgent - process first
async def emergency_alert():
    pass

@fastjob.job(priority=100, queue="background") # Low priority - process last
async def cleanup_old_files():
    pass
```

### Unique Jobs (No Duplicates)

```python
@fastjob.job(unique=True)
async def send_welcome_email(user_email: str):
    # Only one welcome email per user can be queued
    pass

# These return the same job ID - no duplicate processing
job1 = await fastjob.enqueue(send_welcome_email, user_email="alice@example.com")
job2 = await fastjob.enqueue(send_welcome_email, user_email="alice@example.com")
assert job1 == job2  # Same job, queued once
```

### Job Scheduling

```python
from datetime import timedelta, datetime

# Run in 1 hour
await fastjob.schedule(send_reminder, run_in=timedelta(hours=1), user_id=123)

# Run at specific time
await fastjob.schedule(generate_report, run_at=datetime(2025, 12, 25, 9, 0))
```

### Job Management

```python
# Check status
status = await fastjob.get_job_status(job_id)

# Cancel queued jobs
await fastjob.cancel_job(job_id)

# Retry failed jobs
await fastjob.retry_job(job_id)

# Find recent failures
failed_jobs = await fastjob.list_jobs(status="failed", limit=10)
```

## CLI That Doesn't Fight You

### Global API (Recommended for Most Apps)
```bash
# Setup once
fastjob setup

# Run workers
fastjob start --concurrency 4 --queues default,urgent

# Check health
fastjob status --verbose
```

### Instance API (Per-Service)
```bash
# Setup each service database
fastjob setup --database-url="postgresql://localhost/user_service"
fastjob setup --database-url="postgresql://localhost/billing_service"

# Run workers per service
fastjob start --database-url="postgresql://localhost/user_service" --concurrency 2
fastjob start --database-url="postgresql://localhost/billing_service" --concurrency 4

# Monitor each service
fastjob status --database-url="postgresql://localhost/user_service"
fastjob status --database-url="postgresql://localhost/billing_service"
```

Three commands. Both APIs. No complexity.

## Growing Beyond Basic: Pro & Enterprise

As your app scales, upgrade seamlessly:

### FastJob Pro: Recurring Jobs + Dashboard

```python
# Global API - recurring jobs
fastjob.every("10m").do(cleanup_temp_files)
fastjob.schedule("0 9 * * 1-5").job(send_daily_reports)

# Instance API - per-service recurring jobs
user_service.every("5m").do(cleanup_inactive_sessions)
billing_service.schedule("0 2 * * *").job(generate_invoices)
analytics_service.every("1h").do(update_metrics)
```

```bash
# Global API - single dashboard
fastjob dashboard  # http://localhost:6161

# Instance API - dashboard per service
fastjob dashboard --database-url="postgresql://localhost/user_service" --port 6161
fastjob dashboard --database-url="postgresql://localhost/billing_service" --port 6162
fastjob dashboard --database-url="postgresql://localhost/analytics_service" --port 6163
```

### FastJob Enterprise: Production Monitoring

- **Performance metrics** with alerting thresholds
- **Webhook notifications** (Slack, Teams, PagerDuty)
- **Structured logging** for your monitoring stack
- **Dead letter queues** with retry policies
- **SLA monitoring** and compliance reporting

**Upgrade path:** `pip install fastjob-pro` or `fastjob-enterprise` - your code doesn't change.

## Production Deployment Patterns

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

### Multiple Queue Workers
```bash
# Global API - dedicated workers per queue type
fastjob start --queues critical,emails --concurrency 2
fastjob start --queues background --concurrency 1

# Instance API - per-service queue specialization
fastjob start --database-url="postgresql://localhost/user_service" --queues emails,notifications --concurrency 2
fastjob start --database-url="postgresql://localhost/billing_service" --queues payments,invoices --concurrency 4
```

## Migrating from Other Solutions

### From Celery

Celery is powerful and battle-tested, but can be complex for simpler use cases:

```python
# Celery approach
from celery import Celery
app = Celery('myapp', broker='redis://localhost:6379/0')

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def send_email(self, user_email, subject):
    # Runtime parameter validation
    pass

# Requires: Redis setup, separate worker processes, configuration files
# celery -A myapp worker --loglevel=info
```

```python
# FastJob approach
import fastjob

@fastjob.job(retries=3)
async def send_email(user_email: str, subject: str):
    # Built-in type validation, clean async
    pass

# Development: fastjob.start_embedded_worker()
# Production: fastjob start
```

**Key differences:**
- ✅ **No Redis dependency** - uses your existing PostgreSQL
- ✅ **Embedded development mode** - no separate processes locally
- ✅ **Type safety** - Pydantic validation built-in
- ✅ **Native async** - no compatibility layers needed

## Framework Integration

### FastAPI (Recommended)

```python
from fastapi import FastAPI
import fastjob

app = FastAPI()

@fastjob.job()
async def process_upload(file_id: int):
    # Your processing logic
    pass

@app.post("/upload/")
async def upload_file(file_id: int):
    await fastjob.enqueue(process_upload, file_id=file_id)
    return {"status": "processing"}

@app.on_event("startup")
async def startup():
    # ✨ The DX Magic: Same code adapts to any environment
    if fastjob.is_dev_mode():
        fastjob.start_embedded_worker()
        print("🔄 Dev mode: Jobs process instantly in your FastAPI app")
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

## Configuration (Minimal by Design)

FastJob works with almost zero configuration - this is intentional:

```bash
# Required: Database connection (you probably already have this)
export FASTJOB_DATABASE_URL="postgresql://user:password@localhost/myapp"

# Optional: Development mode
export FASTJOB_DEV_MODE=true
```

That's it. Everything else has sensible defaults.

**Advanced options** (when you need them):
```bash
# Job cleanup (default: 5 minutes)
export FASTJOB_RESULT_TTL=300

# Logging level
export FASTJOB_LOG_LEVEL="INFO"

# Custom job module location
export FASTJOB_JOBS_MODULE="myapp.jobs"
```

## Testing

```bash
pip install -e ".[dev]"
createdb fastjob_test
python run_tests.py  # Recommended - organized test runner
# or: python -m pytest tests/ -v
```

## Documentation & Resources

📖 **[Complete Documentation](https://fastjob.dev)** - Everything from getting started to production deployment  
🔄 **[Framework Integration](https://fastjob.dev/docs/fastapi-integration)** - FastAPI, Django, Flask, and more  
⚡ **[Your First Job](https://fastjob.dev/docs/first-job)** - Working example in under 5 minutes  
🔍 **[Compare with Others](https://fastjob.dev/compare)** - Detailed comparisons with Celery, RQ, Dramatiq  

## Why I Built This

I've been building web apps for years, and every single time I needed background jobs, I'd end up spending way too much time on infrastructure instead of actual features.

Redis queues are fast but lose jobs during network hiccups. Database queues are reliable but usually have terrible APIs. I wanted something that combined PostgreSQL's reliability with an API that felt like writing normal Python.

FastJob is what I wish I had when I started building background job systems. It's the tool I reach for now, and the one I wish existed five years ago.


## Contributing

Found a bug? Want a feature? I'd love to hear from you:

- **Issues**: GitHub Issues for bugs and feature requests
- **Email**: abhinav@apiclabs.com for questions and Pro/Enterprise licensing
- **Twitter**: [@abhinav](https://twitter.com/abhinav)

## License

MIT - use it however you want.

---

**FastJob** - Background jobs that just work.

Built by [Abhinav Saxena](https://github.com/abhinavs)