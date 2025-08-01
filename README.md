# FastJob

**Because your background jobs shouldn't be a background worry.**

You know the pain: spending hours wrestling with Celery's maze of configuration files, setting up Redis just to send an email, debugging why your development worker randomly stopped, or watching jobs vanish when Redis hiccups in production.

I built FastJob because I got tired of that complexity. Your PostgreSQL database is already bulletproof – why not use it for jobs too? FastJob is what happens when you prioritize developer happiness over enterprise feature checklists.

It's the job queue for developers who believe **simple is beautiful**.

## FastJob vs The Reality You're Living

| Pain Point           | Celery                    | RQ                     | FastJob                    |
| -------------------- | ------------------------- | ---------------------- | -------------------------- |
| **Setup Nightmare**  | Redis / RabbitMQ setup    | Redis required         | ✅ Uses your PostgreSQL    |
| **Dev Workflow**     | Separate worker process   | Separate process       | ✅ Embedded in your app    |
| **Type Disasters**   | Runtime job failures      | Runtime failures       | ✅ Pydantic validation     |
| **Async Hell**       | Sync/async impedance      | Sync-only (it's 2025!) | ✅ Native asyncio          |
| **Microservices**    | Shared queues = chaos     | Manual separation      | ✅ Database per service    |
| **Multi-Tenant**     | Manual isolation          | Not supported          | ✅ Database per tenant     |
| **Monitoring**       | Flower (another service)  | Basic tools            | ✅ Built-in dashboard (Pro) |
| **Scheduling**       | Celery Beat complexity    | External cron          | ✅ In-code cron (Pro)      |
| **Learning Curve**   | Weeks to get right        | Days to understand     | ✅ Minutes to productivity |

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

## 30-Second Setup (Actually)

```bash
pip install fastjob
createdb your_app_db
export FASTJOB_DATABASE_URL="postgresql://localhost/your_app_db"
fastjob setup
```

Your jobs are ready to run. Really.

## The Development Experience You've Been Wanting

### Your First Working Example

Create `jobs.py`:
```python
import asyncio
import fastjob

@fastjob.job()
async def send_welcome_email(user_email: str, name: str):
    print(f"📧 Sending welcome to {name} at {user_email}")
    await asyncio.sleep(1)  # Simulate email API call
    print(f"✅ Email sent!")

@fastjob.job(retries=3, queue="payments")
async def process_payment(order_id: int, amount: float):
    print(f"💳 Processing ${amount} for order {order_id}")
    await asyncio.sleep(2)  # Simulate payment API
    print(f"✅ Payment processed!")
```

Create `main.py`:
```python
import asyncio
from jobs import send_welcome_email, process_payment
import fastjob

async def main():
    print("🚀 Enqueueing jobs...")

    await fastjob.enqueue(send_welcome_email,
                         user_email="alice@example.com",
                         name="Alice")

    await fastjob.enqueue(process_payment,
                         order_id=12345,
                         amount=99.99)

    print("✅ Jobs queued! Check your worker terminal.")

if __name__ == "__main__":
    asyncio.run(main())
```

Run it:
```bash
# Terminal 1: Start worker
fastjob start

# Terminal 2: Enqueue jobs
python main.py
```

**Watch your jobs process instantly.** No Redis setup. No configuration hell. Just working code.

## Development vs Production: Same Code, Zero Complexity

The beautiful thing? Your job code never changes. Only the worker management does:

### Development: Everything Just Works

```python
from fastapi import FastAPI
import fastjob

app = FastAPI()

@fastjob.job(retries=3)
async def resize_uploaded_image(user_id: int, image_path: str):
    # Your image processing logic
    pass

@app.post("/upload-photo/")
async def upload_photo(user_id: int, image_data: bytes):
    image_path = save_image(image_data)

    # Enqueue background job - it just works
    await fastjob.enqueue(resize_uploaded_image,
                         user_id=user_id,
                         image_path=image_path)

    return {"status": "uploaded", "processing": "queued"}

@app.on_event("startup")
async def startup():
    if fastjob.run_in_dev_mode():
        # Jobs run in your web server - no separate processes
        fastjob.start_embedded_worker()
```

**Development:** `FASTJOB_DEV_MODE=true python -m uvicorn main:app`

Jobs process in your web server. No Docker. No separate terminals. No complexity.

### Production: Independent Scaling

```bash
# Your app runs normally (same code!)
python -m uvicorn main:app

# Separate terminal: dedicated job workers
fastjob start --concurrency 4 --queues default,urgent
```

**Same functions. Same enqueue calls. Just different worker deployment.**

## Two APIs: Start Simple, Scale to Microservices

FastJob grows with your architecture. Start simple, scale when you need isolation:

### 🎯 Global API (Most Teams)

Perfect for single applications:

```python
import fastjob

# One database, simple configuration
@fastjob.job()
async def send_email(to: str, subject: str):
    pass

await fastjob.enqueue(send_email, to="user@example.com", subject="Welcome!")
```

### 🏗️ Instance API (Microservices/Multi-Tenant)

When you need **complete isolation**:

```python
from fastjob import FastJob

# Each service gets its own database and job processing
user_service = FastJob(database_url="postgresql://localhost/user_service")
billing_service = FastJob(database_url="postgresql://localhost/billing_service")
analytics_service = FastJob(database_url="postgresql://localhost/analytics_service")

@user_service.job()
async def send_welcome_email(user_id: int):
    pass

@billing_service.job()
async def process_payment(invoice_id: int):
    pass

@analytics_service.job()
async def track_event(event_data: dict):
    pass

# Each service processes its own jobs independently
await user_service.enqueue(send_welcome_email, user_id=123)
await billing_service.enqueue(process_payment, invoice_id=456)
await analytics_service.enqueue(track_event, event_data={...})
```

**Why this is powerful:**
- 🔒 **Complete isolation** - user service can't accidentally process billing jobs
- 📊 **Independent monitoring** - dashboard per service shows exactly what you need
- 🚀 **Independent scaling** - scale payment processing differently from analytics
- 👥 **Team ownership** - different teams own different services completely
- 🛡️ **Data security** - tenant data never crosses service boundaries

**When to use which:**
- **Global API**: Single app, shared database (90% of teams start here)
- **Instance API**: Microservices, multi-tenant SaaS, or when you need job isolation

**Migration path:** Start Global, migrate services to Instance as your architecture evolves.

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

### Global API (Single Database)
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

## Escape from Celery Hell

### What You're Probably Dealing With Now

```python
# Celery (the pain you know)
from celery import Celery
app = Celery('myapp', broker='redis://localhost:6379/0')

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def send_email(self, user_email, subject):
    # No type safety, runtime failures
    pass

# Separate Redis setup, worker processes, configuration files...
# celery -A myapp worker --loglevel=info
```

### What You Get With FastJob

```python
# FastJob (the relief you need)
import fastjob

@fastjob.job(retries=3)
async def send_email(user_email: str, subject: str):
    # Type safety, clean async, no self parameter
    pass

# Development: fastjob.start_embedded_worker()
# Production: fastjob start
```

**The difference:**
- ✅ **No Redis** - uses your reliable PostgreSQL
- ✅ **No separate config** - everything in your Python code
- ✅ **Type safety** - catch errors before jobs run
- ✅ **Clean async** - no sync/async bridging hell
- ✅ **Simple development** - jobs run in your web server process

## Framework Integration

### FastAPI (Perfect Match)

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

## Configuration (The Minimal Kind)

FastJob works with almost zero configuration:

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
python -m pytest tests/ -v
```

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