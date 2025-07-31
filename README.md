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

## 2-Minute Quickstart

Copy, paste, run. That's it.

```bash
# Install and setup (30 seconds)
pip install fastjob
export FASTJOB_DATABASE_URL="postgresql://localhost/postgres"  # Use existing DB
fastjob setup
```

```python
# Create demo.py (30 seconds)
import fastjob

@fastjob.job()
async def say_hello(name: str):
    print(f"Hello {name}!")

async def main():
    # Queue and process jobs in development mode
    await fastjob.enqueue(say_hello, name="World")
    await fastjob.run_worker(run_once=True)  # Process jobs once and exit

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

```bash
# Run it (10 seconds)
python demo.py
# Output: Hello World!
```

**That's it.** One file, one command, job done.

For production, just run `fastjob start` in a separate process instead of `run_once=True`.

### Development vs Production: Write Once, Run Anywhere

The best part? I hate having different code paths for dev and prod, so I made sure you don't need them.

```python
# Stick this in your app startup and forget about it
if fastjob.is_dev_mode():
    fastjob.start_embedded_worker()
```

**Development:** `FASTJOB_DEV_MODE=true` → jobs run inside your app (no extra processes)  
**Production:** Leave that env var unset → run `fastjob start` in separate processes

```bash
# Production: spin up dedicated workers
fastjob start --concurrency 4 --queues urgent,background
```

Your job functions don't change. Your enqueue calls don't change. Nothing changes except how the workers run.

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

## Two Ways to Use FastJob

Most people start with the Global API (it's simpler), but if you're building microservices or need multiple databases, the Instance API gives you more control.

### Global API (Start here)

This is the "just import and go" approach. Perfect for most apps:

```python
import fastjob

# Set this up once when your app starts
fastjob.configure(database_url="postgresql://localhost/myapp")

# Then define jobs anywhere in your codebase
@fastjob.job(retries=3, queue="emails")
async def send_email(to: str, subject: str, body: str):
    # Your email logic here
    print(f"Sending email to {to}: {subject}")
    # Simulate email sending
    await asyncio.sleep(1)
    return {"status": "sent", "to": to}

@fastjob.job(retries=5, queue="payments")
async def process_payment(order_id: int, amount: float):
    # Payment processing logic
    return {"order_id": order_id, "amount": amount, "status": "processed"}

# Enqueue jobs from anywhere in your application
async def handle_user_signup(user_email: str, user_name: str):
    # Enqueue welcome email
    email_job_id = await fastjob.enqueue(
        send_email,
        to=user_email,
        subject="Welcome!",
        body=f"Hello {user_name}, welcome to our platform!"
    )
    
    # Check job status
    status = await fastjob.get_job_status(email_job_id)
    print(f"Email job status: {status}")

# Worker management - same code, different environments
if fastjob.is_dev_mode():
    await fastjob.start_embedded_worker()
# Production: fastjob start --concurrency 4 (CLI)
```

What you get:
- One shared job registry for your whole app
- Configure once, use everywhere
- Just `import fastjob` and you're ready to go

### Instance-Based API (For microservices and multi-tenant apps)

When you need multiple isolated job queues, create separate FastJob instances:

```python
from fastjob import FastJob

# Say you have a user service and an order service
user_service = FastJob(
    database_url="postgresql://localhost/user_service",
    default_concurrency=2,
    result_ttl=600
)

order_service = FastJob(
    database_url="postgresql://localhost/order_service", 
    default_concurrency=4,
    result_ttl=3600
)

# Each service gets its own job registry and workers
@user_service.job(retries=3, queue="user_tasks")
async def send_welcome_email(user_id: int, email: str):
    print(f"Sending welcome email to user {user_id}: {email}")
    # Your email sending logic here
    return {"user_id": user_id, "email_sent": True}

@order_service.job(retries=2, queue="order_processing")
async def process_payment(order_id: int, amount: float):
    print(f"Processing payment for order {order_id}: ${amount}")
    # Your payment processing logic here
    return {"order_id": order_id, "amount": amount, "status": "processed"}

# Each service enqueues to its own instance
async def handle_user_signup(user_id: int, email: str):
    job_id = await user_service.enqueue(send_welcome_email, user_id=user_id, email=email)
    return {"service": "user", "job_id": job_id}

async def handle_new_order(order_id: int, amount: float):
    job_id = await order_service.enqueue(process_payment, order_id=order_id, amount=amount)
    return {"service": "order", "job_id": job_id}

# Worker management - same code, different environments
if fastjob.is_dev_mode():
    # Development: embedded workers in app process
    await asyncio.gather(
        user_service.start_embedded_worker(concurrency=2, queues=["user_tasks"]),
        order_service.start_embedded_worker(concurrency=4, queues=["order_processing"])
    )

# Production: separate CLI worker processes (no code changes!)
# fastjob start --database-url="postgresql://localhost/user_service" --concurrency 2 --queues user_tasks  
# fastjob start --database-url="postgresql://localhost/order_service" --concurrency 4 --queues order_processing

# Important: Clean shutdown
async def shutdown():
    await user_service.close()
    await order_service.close()
```

What you get:
- Completely separate job queues and databases
- Each service can have different settings
- Perfect isolation for testing and deployment
- You handle connections yourself (call `await app.close()` when done)

### Quick Comparison

| Aspect | Global API | Instance-Based API |
|--------|------------|-------------------|
| **Configuration** | `fastjob.configure()` once | Per-instance in constructor |
| **Job Registry** | Single global registry | Isolated per instance |
| **Memory Usage** | Lower (single instance) | Higher (multiple instances) |
| **Connection Pooling** | Shared global pool | Separate pool per instance |
| **Cleanup** | Automatic | Manual `await app.close()` |
| **Multi-tenancy** | Not suitable | Perfect fit |
| **Testing** | Simpler setup | More flexible isolation |
| **Debugging** | Single point of configuration | Multiple configurations to track |

### Which One Should You Use?

**Start with Global API if:**
- You have one database
- You're building a typical web app
- You want the easiest setup
- You're just getting started

**Go with Instance-Based API if:**
- You're doing microservices (different databases per service)
- You need complete isolation between parts of your app
- You're building multi-tenant apps
- You're embedding FastJob in a library

### Can I Mix Both?

Yeah, absolutely:

```python
import fastjob
from fastjob import FastJob

# Global API for main application jobs
fastjob.configure(database_url="postgresql://localhost/main_app")

@fastjob.job()
async def main_app_job():
    pass

# Instance API for specific service handling
payment_service = FastJob(database_url="postgresql://localhost/payment_service")

@payment_service.job()
async def process_payment():
    pass

# Use both
await fastjob.enqueue(main_app_job)
await payment_service.enqueue(process_payment)
```

**Best Practice**: Start with the Global API for simplicity, then migrate specific use cases to Instance-Based API as your needs become more complex.

### CLI for Both APIs

**Global API + CLI:**
```bash
# Set your database URL once
export FASTJOB_DATABASE_URL="postgresql://localhost/myapp"

# Then use CLI commands normally
fastjob setup
fastjob start --concurrency 4
fastjob status
```

**Instance-Based API + CLI:**

I added `--database-url` support so you can target specific databases:

```bash
# Setup databases for different services
fastjob setup --database-url="postgresql://localhost/user_service"
fastjob setup --database-url="postgresql://localhost/order_service"

# Start workers for specific services
fastjob start --database-url="postgresql://localhost/user_service" --concurrency 2 --queues user_tasks
fastjob start --database-url="postgresql://localhost/order_service" --concurrency 4 --queues order_processing
```

**Microservices application example:**
```python
# Your application uses instance-based API for different services
user_service = FastJob(database_url="postgresql://localhost/user_service")
order_service = FastJob(database_url="postgresql://localhost/order_service")

@user_service.job(queue="user_tasks")
async def send_welcome_email(user_id: int, email: str):
    # Send welcome email logic
    return {"user_id": user_id, "email_sent": True}

@order_service.job(queue="order_processing")
async def process_payment(order_id: int, amount: float):
    # Payment processing logic
    return {"order_id": order_id, "processed": True}
```

```bash
# Workers for each service (no code changes needed!)
fastjob start --database-url="postgresql://localhost/user_service" --queues user_tasks
fastjob start --database-url="postgresql://localhost/order_service" --queues order_processing
```

**Key benefits:**
- ✅ **No hybrid setup needed** - CLI works directly with any database
- ✅ **No environment variable juggling** - specify database per command
- ✅ **Perfect for microservices** - each worker targets specific service database
- ✅ **Same job code** - your `@service.job()` functions work unchanged

## More useful stuff

**Automatic type validation** with Pydantic models:

```python
class EmailJobArgs(BaseModel):
    to: str
    subject: str
    user_id: int

@fastjob.job(args_model=EmailJobArgs)
async def send_email(to: str, subject: str, user_id: int):
    # FastJob validates arguments before your job runs
    pass
```

**Priority queues** for when some jobs matter more:

```python
@fastjob.job(priority=1, queue="critical")    # High priority
async def emergency_alert():
    pass

@fastjob.job(priority=100, queue="background") # Low priority
async def cleanup_old_files():
    pass
```

**Unique jobs** to avoid duplicates:

```python
@fastjob.job(unique=True)
async def send_welcome_email(user_email: str):
    # FastJob won't queue this twice for the same email
    pass

# These return the same job ID - no duplicate created
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

FastJob provides simple commands for all operations:

```bash
# Setup database (run once)
fastjob setup

# Start worker process
fastjob start --concurrency 4 --queues default,urgent

# Check system status
fastjob status --verbose --jobs

# Monitor workers (production)
fastjob workers --stale --cleanup
```

**Command details:**

- **`fastjob setup`** - Initialize/update database schema
- **`fastjob start`** - Start worker to process jobs
- **`fastjob status`** - Show system health, job stats, and queue info
- **`fastjob workers`** - Monitor worker heartbeats and health (production monitoring)

## Configuration

Two settings you need to know about:

```bash
# Your database (required)
export FASTJOB_DATABASE_URL="postgresql://localhost/myapp"

# Development mode (optional, makes workers run in your app)
export FASTJOB_DEV_MODE=true
```

**That's it.** Everything else has sensible defaults.

Need to customize something? Here are the other options:

```bash
export FASTJOB_RESULT_TTL=300        # Keep completed jobs for 5 minutes (0 = delete immediately)
export FASTJOB_JOBS_MODULE="myapp.tasks"  # Where to find @job functions (default: auto-discover)
export FASTJOB_LOG_LEVEL="DEBUG"    # Logging level (default: INFO)
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

## Worker Monitoring & Heartbeats

FastJob includes worker heartbeats for production monitoring. Workers register themselves and send periodic heartbeats to detect failures and provide operational visibility.

**Basic monitoring:**
```bash
# Check system status (includes worker summary)
fastjob status

# View detailed worker information  
fastjob workers

# Clean up stale worker records
fastjob workers --cleanup
```

**Key benefits:**
- Detect crashed workers immediately (OOM, segfaults, container kills)
- Real-time worker status for monitoring and alerting
- Automatic cleanup of stale worker records
- Accurate worker counts for autoscaling decisions

Workers heartbeat every 5 seconds and are considered stale after 5 minutes of no contact. See `examples/production/` for detailed monitoring and automation examples.

## Production-Ready Features

FastJob is thoroughly tested and battle-ready for production deployments:

**✅ Robust Error Handling**: Graceful handling of corrupted data, JSON parsing errors, and validation failures without blocking the queue

**✅ Worker Heartbeat System**: Complete worker monitoring with registration, heartbeat updates, failure detection, and automatic cleanup

**✅ Connection Management**: Sophisticated database connection pooling with proper isolation and context management

**✅ LISTEN/NOTIFY Optimization**: Efficient job pickup using PostgreSQL's LISTEN/NOTIFY for instant job processing

**✅ Comprehensive CLI**: Full command-line interface with plugin support, error handling, and production monitoring tools

**✅ Multi-API Architecture**: Both global and instance-based APIs for different deployment patterns

**✅ TTL & Cleanup**: Automatic cleanup of completed jobs with configurable retention policies

All features are covered by 373 automated tests ensuring reliability in production environments.

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

# Same code, different environments  
if fastjob.is_dev_mode():
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

**Global API approach:**

```python
from fastapi import FastAPI
import fastjob

app = FastAPI()

# Configure FastJob once at startup
@app.on_event("startup")
async def startup():
    fastjob.configure(database_url="postgresql://localhost/myapp")
    
    # Automatic worker management based on environment
    if fastjob.is_dev_mode():
        await fastjob.start_embedded_worker()

@fastjob.job()
async def process_upload(file_id: int):
    # Process file in background
    pass

@app.post("/upload/")
async def upload_file(file_id: int):
    await fastjob.enqueue(process_upload, file_id=file_id)
    return {"status": "processing"}
```

**Instance-based approach (multi-tenant):**

```python
from fastapi import FastAPI, Depends
from fastjob import FastJob

app = FastAPI()

# Create tenant-specific FastJob instances
tenant_jobs = {}

async def get_tenant_fastjob(tenant_id: str) -> FastJob:
    if tenant_id not in tenant_jobs:
        tenant_jobs[tenant_id] = FastJob(
            database_url=f"postgresql://localhost/tenant_{tenant_id}"
        )
    return tenant_jobs[tenant_id]

@app.post("/upload/{tenant_id}")
async def upload_file(
    tenant_id: str, 
    file_id: int,
    fastjob_app: FastJob = Depends(get_tenant_fastjob)
):
    # Define job inline or use tenant-specific registry
    @fastjob_app.job()
    async def process_upload(file_id: int):
        # Tenant-specific processing logic
        pass
    
    await fastjob_app.enqueue(process_upload, file_id=file_id)
    return {"status": "processing", "tenant": tenant_id}

@app.on_event("shutdown")
async def shutdown():
    # Clean shutdown for all tenant instances
    for fastjob_app in tenant_jobs.values():
        await fastjob_app.close()
```

### Django

**Global API approach:**

```python
# settings.py - Configure FastJob
import fastjob

fastjob.configure(
    database_url="postgresql://localhost/django_app"
)

# jobs.py - Define your jobs
import fastjob

@fastjob.job()
async def send_notification(user_id: int):
    # Send notification logic
    pass

# views.py - Use in views
from django.http import JsonResponse
from .jobs import send_notification
import fastjob

async def trigger_notification(request):
    user_id = request.POST.get('user_id')
    await fastjob.enqueue(send_notification, user_id=int(user_id))
    return JsonResponse({"status": "queued"})
```

### Flask

**Global API approach:**

```python
from flask import Flask
import fastjob
import asyncio

app = Flask(__name__)

# Configure FastJob at app startup
@app.before_first_request
def configure_fastjob():
    fastjob.configure(database_url="postgresql://localhost/flask_app")

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

**Instance-based approach:**

```python
from flask import Flask, g
from fastjob import FastJob
import asyncio

app = Flask(__name__)

def get_fastjob():
    if 'fastjob' not in g:
        g.fastjob = FastJob(database_url="postgresql://localhost/flask_app")
    return g.fastjob

@app.teardown_appcontext
def close_fastjob(error):
    fastjob_app = g.pop('fastjob', None)
    if fastjob_app is not None:
        asyncio.run(fastjob_app.close())

@app.route('/trigger')
def trigger():
    fastjob_app = get_fastjob()
    
    @fastjob_app.job()
    async def background_task(data: str):
        return f"Processed: {data}"
    
    asyncio.run(fastjob_app.enqueue(background_task, data="test"))
    return {"status": "queued"}
```

## Testing

```bash
pip install -e ".[dev]"
createdb fastjob_test
python run_tests.py  # Run full test suite (~2 minutes)
```

## Why I built this

After years of wrestling with Celery configs and Redis setups just to send an email in the background, I got tired of the complexity. Redis queues are fast but lose jobs when things go wrong. Database queues are reliable but usually have terrible APIs.

I wanted something that just worked: reliable like PostgreSQL, simple like the good parts of Celery, and built for async Python from day one. FastJob is what I wish I had when I was building my first async web apps.

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
