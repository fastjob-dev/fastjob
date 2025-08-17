# FastJob

**PostgreSQL-only async job queue - built for developer happiness**

If you've worked with background jobs in Python, you know the drill: install Redis, configure Celery, set up separate worker processes, debug sync/async compatibility issues, and hope your jobs don't disappear when something goes wrong.

I built FastJob with a different philosophy: your PostgreSQL database is already handling your app's most critical data reliably – why not use it for jobs too? FastJob prioritizes developer productivity and simplicity over enterprise feature checklists.

It's the job queue for developers who believe **simple is beautiful**.

## FastJob vs. The Old Way

| Aspect              | Celery                             | RQ                      | FastJob                      |
| ------------------- | ---------------------------------- | ----------------------- | ---------------------------- |
| **Infrastructure**  | Redis/RabbitMQ required            | Redis required          | ✅ Uses your PostgreSQL      |
| **Development**     | Separate worker process            | Separate process        | ✅ Embedded in your app      |
| **Type Safety**     | Manual validation                  | Manual validation       | ✅ Automatic with Pydantic   |
| **Async Support**   | Requires compatibility layer       | Sync-only design        | ✅ Native asyncio            |
| **Microservices**   | Shared queue coordination          | Manual queue separation | ✅ Database per service      |
| **Multi-Tenant**    | Custom isolation logic             | Limited support         | ✅ Database per tenant       |
| **Monitoring**      | Flower (separate service)          | Basic CLI tools         | ✅ Built-in dashboard (Pro)  |
| **Scheduling**      | Celery Beat (additional component) | External cron needed    | ✅ In-code definitions (Pro) |
| **Getting Started** | Significant setup time             | Moderate setup          | ✅ Minutes to first job      |

## Quick Start

**Prerequisites:** PostgreSQL (most developers already have this)

```bash
# 1. Install FastJob
pip install git+https://github.com/fastjob-dev/fastjob.git

# 2. Set your database URL
export FASTJOB_DATABASE_URL="postgresql://localhost/your_existing_db"

# 3. Run migration (creates necessary tables in your database)
fastjob setup
```

Create `demo.py`:

```python
import asyncio
import fastjob

# 1. Decorate any async function
@fastjob.job(retries=3)
async def send_email(email: str, name: str):
    print(f"📧 Sending to {name} at {email}")
    await asyncio.sleep(1)  # Simulate work
    print(f"✅ Sent!")

async def main():
    # 2. The DX Magic: Same code adapts to any environment
    if fastjob.is_dev_mode():
        fastjob.start_embedded_worker()
        print("🔄 Dev mode: Jobs process instantly in your app")

    # 3. Enqueue jobs anywhere
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
fastjob start --concurrency=4
```

**🚀 Write once, run anywhere** - environment variables control worker behavior, your code stays the same.

## How It Works: Core Concepts

### The DX Magic: Automatic Dev/Prod Environments

FastJob automatically adapts to your environment with zero code changes:

- **Development**: Set `FASTJOB_DEV_MODE=true` and jobs run immediately in your application process via an embedded worker
- **Production**: Remove the environment variable and jobs queue for separate worker processes
- **Same code, zero configuration changes** - the ultimate developer experience

```python
# This same code works everywhere:
if fastjob.is_dev_mode():
    fastjob.start_embedded_worker()  # Dev: runs in your app
# Production: jobs queue for external workers automatically
```

### Two APIs: Global vs. Instance

Choose the API style that fits your architecture:

**Global API (Most Apps):**

```python
import fastjob

@fastjob.job()
async def send_email(to: str, subject: str):
    pass

await fastjob.enqueue(send_email, to="user@example.com", subject="Welcome!")
```

**Instance API (Microservices):**

```python
from fastjob import FastJob

user_service = FastJob(database_url="postgresql://localhost/users")
billing_service = FastJob(database_url="postgresql://localhost/billing")

@user_service.job()
async def send_welcome_email(user_id: int):
    pass

@billing_service.job()
async def process_payment(payment_id: int):
    pass

await user_service.enqueue(send_welcome_email, user_id=123)
await billing_service.enqueue(process_payment, payment_id=456)
```

Perfect for microservices, multi-tenant SaaS, and team separation.

## Key Features

### ✅ **Zero Infrastructure Headaches**

```python
# No Redis to install, no message broker to configure
export FASTJOB_DATABASE_URL="postgresql://localhost/myapp"
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

### ✅ **Native Async Support**

```python
# Write normal async code - no compatibility layers
@fastjob.job()
async def process_upload(file_data: bytes):
    async with aiofiles.open("processed.jpg", "wb") as f:
        await f.write(await process_image(file_data))
```

### ✅ **Advanced Job Features**

```python
# Priority queues
@fastjob.job(priority=1, queue="critical")
async def emergency_alert():
    pass

# Unique jobs (no duplicates)
@fastjob.job(unique=True)
async def send_welcome_email(user_email: str):
    pass

# Job scheduling
from datetime import timedelta
await fastjob.schedule(send_reminder, run_in=timedelta(hours=1), user_id=123)
```

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
    if fastjob.is_dev_mode():
        fastjob.start_embedded_worker()
        print("🔄 Dev mode: Jobs process instantly in your FastAPI app")
```

### Django

```python
from django.http import JsonResponse
import fastjob
import asyncio

@fastjob.job()
async def send_notification(user_id: int):
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
    pass

@app.route('/trigger')
def trigger():
    asyncio.run(fastjob.enqueue(background_task, data="test"))
    return {"status": "queued"}
```

## The Command Line Interface (CLI)

### Setup and Workers

```bash
# Initial database setup (creates tables)
fastjob setup

# Start workers
fastjob start --concurrency 4 --queues default,urgent

# Check status
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
```

### Monitoring

```bash
# Show system status and queue statistics
fastjob status --verbose --jobs

# Show worker status and heartbeats
fastjob workers --stale

# Clean up stale worker records
fastjob workers --cleanup
```

## Production & Deployment

### Environment Variables

```bash
# Required
export FASTJOB_DATABASE_URL="postgresql://user:pass@host:5432/db"

# Optional: Development mode
export FASTJOB_DEV_MODE=true

# Advanced options (when you need them)
export FASTJOB_RESULT_TTL=300        # Job cleanup (default: 5 minutes)
export FASTJOB_LOG_LEVEL="INFO"      # Logging level
export FASTJOB_POOL_SIZE=20          # Connection pool size
```

### Systemd Service

```ini
[Unit]
Description=FastJob Worker
After=postgresql.service

[Service]
Type=simple
User=myapp
Environment=FASTJOB_DATABASE_URL=postgresql://user:pass@localhost/myapp
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
# Dedicated workers per queue type
fastjob start --queues critical,emails --concurrency 2
fastjob start --queues background --concurrency 1

# Instance API - per-service specialization
fastjob start --database-url="postgresql://localhost/user_service" --queues emails,notifications --concurrency 2
fastjob start --database-url="postgresql://localhost/billing_service" --queues payments,invoices --concurrency 4
```

## Upgrading to Pro & Enterprise

**FastJob Community** (Free): Perfect for most applications

- Async job processing
- Type-safe job definitions
- Built-in retries and error handling
- Development embedded worker

**FastJob Pro**: Advanced scheduling and monitoring

- **Built-in dashboard** with real-time job monitoring
- **Recurring jobs** with in-code cron definitions
- **Advanced scheduling** (delays, dependencies, batching)
- **Performance analytics** and queue insights

```python
# Global API - recurring jobs
fastjob.every("10m").do(cleanup_temp_files)
fastjob.schedule("0 9 * * 1-5").job(send_daily_reports)

# Instance API - per-service recurring jobs
user_service.every("5m").do(cleanup_inactive_sessions)
billing_service.schedule("0 2 * * *").job(generate_invoices)
```

**FastJob Enterprise**: Production-grade reliability

- **Multi-tenant job isolation** with database-level separation
- **Dead letter queues** with retry policies
- **SLA monitoring** and compliance reporting
- **Webhook notifications** (Slack, Teams, PagerDuty)

**Upgrade path:** `pip install fastjob-pro` or `fastjob-enterprise` - your code doesn't change.

## Configuration

FastJob uses environment variables for configuration. Set `FASTJOB_DATABASE_URL` and you're ready:

```bash
# Required
export FASTJOB_DATABASE_URL="postgresql://localhost/myapp"

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

# Connection pool settings
export FASTJOB_POOL_SIZE=20
export FASTJOB_MAX_OVERFLOW=10
```

## Testing

```bash
pip install -e ".[dev]"
createdb fastjob_test
python run_tests.py  # Recommended - organized test runner
# or: python -m pytest tests/ -v
```

## Migrating from Celery

FastJob offers a cleaner, simpler alternative to Celery:

**Before (Celery):**

```python
from celery import Celery

app = Celery('myapp', broker='redis://localhost:6379')

@app.task
def send_email(to, subject, body):
    # Manual validation, sync-only
    pass

# Enqueue
send_email.delay(to="user@example.com", subject="Hello", body="...")
```

**After (FastJob):**

```python
import fastjob

@fastjob.job()
async def send_email(to: str, subject: str, body: str):
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

**FastJob** - Simple is beautiful.

Built by [Abhinav Saxena](https://github.com/abhinavs)
