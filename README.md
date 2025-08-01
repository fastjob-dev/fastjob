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
| **Microservices**    | Complex routing config    | Manual queue separation | ✅ Instance API (separate DBs) |
| **Multi-Tenant**     | Manual tenant isolation   | No built-in support     | ✅ Database-per-tenant isolation |
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
echo "FASTJOB_DATABASE_URL=postgresql://localhost/postgres" > .env
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

## Instance API Setup (Microservices & Multi-Tenant)

Need separate job queues for different services or tenants? FastJob's Instance API gives you complete isolation with zero complexity.

### When to Use Instance API

**Choose Instance API when you have:**
- Microservices architecture with separate databases
- Multi-tenant applications requiring data isolation  
- Different job processing rules per service
- Independent scaling requirements per service

**Stick with Global API when you have:**
- Single application with one job queue
- Simple background job processing
- Getting started with FastJob

### Instance API Quickstart

```bash
# 1. Create separate databases for each service
createdb user_service
createdb payment_service
createdb notification_service

# 2. Setup each service database
fastjob setup --database-url="postgresql://localhost/user_service"
fastjob setup --database-url="postgresql://localhost/payment_service"  
fastjob setup --database-url="postgresql://localhost/notification_service"
```

```python
# 3. Create service-specific FastJob instances
from fastjob import FastJob

# Each service gets its own isolated job queue
user_service = FastJob(database_url="postgresql://localhost/user_service")
payment_service = FastJob(database_url="postgresql://localhost/payment_service")
notification_service = FastJob(database_url="postgresql://localhost/notification_service")

# Register jobs with specific services
@user_service.job()
async def process_user_signup(user_id: str, email: str):
    print(f"Processing user signup: {email}")
    # Only accesses user service database
    return f"User {user_id} created"

@payment_service.job()
async def process_payment(payment_id: str, amount: float):
    print(f"Processing payment: ${amount}")
    # Only accesses payment service database  
    return f"Payment {payment_id} processed"

@notification_service.job()
async def send_welcome_email(user_id: str, email: str):
    print(f"Sending welcome email to: {email}")
    # Only accesses notification service database
    return f"Email sent to {email}"

async def main():
    # Enqueue jobs to specific services
    user_job = await user_service.enqueue(
        process_user_signup, 
        user_id="123", 
        email="user@example.com"
    )
    
    payment_job = await payment_service.enqueue(
        process_payment,
        payment_id="pay_456", 
        amount=99.99
    )
    
    # Cross-service workflow
    notification_job = await notification_service.enqueue(
        send_welcome_email,
        user_id="123",
        email="user@example.com"
    )
    
    print(f"Jobs queued: {user_job}, {payment_job}, {notification_job}")
```

```bash
# 4. Run workers for each service (production)
fastjob worker --database-url="postgresql://localhost/user_service" --concurrency 2
fastjob worker --database-url="postgresql://localhost/payment_service" --concurrency 1  
fastjob worker --database-url="postgresql://localhost/notification_service" --concurrency 4

# 5. Monitor each service independently
fastjob dashboard --database-url="postgresql://localhost/user_service" --port 6161
fastjob dashboard --database-url="postgresql://localhost/payment_service" --port 6162
fastjob dashboard --database-url="postgresql://localhost/notification_service" --port 6163
```

### Multi-Tenant Setup

For multi-tenant applications, create database-per-tenant for maximum isolation:

```python
from fastjob import FastJob

# Tenant-specific instances
tenant_a = FastJob(database_url="postgresql://localhost/tenant_a_jobs")
tenant_b = FastJob(database_url="postgresql://localhost/tenant_b_jobs")

@tenant_a.job()
async def process_tenant_data(data_id: str):
    # Only accesses Tenant A's data - complete isolation
    pass

@tenant_b.job()  
async def process_tenant_data(data_id: str):
    # Only accesses Tenant B's data - completely separate
    pass

# Same job name, different tenants, zero cross-contamination
await tenant_a.enqueue(process_tenant_data, data_id="123")
await tenant_b.enqueue(process_tenant_data, data_id="123")  # Different "123"
```

### Environment Configuration

Use environment variables for flexible deployment:

```bash
# Development
export USER_SERVICE_DATABASE_URL="postgresql://localhost/user_service_dev"
export PAYMENT_SERVICE_DATABASE_URL="postgresql://localhost/payment_service_dev"

# Production  
export USER_SERVICE_DATABASE_URL="postgresql://prod-user-db:5432/jobs"
export PAYMENT_SERVICE_DATABASE_URL="postgresql://prod-payment-db:5432/jobs"
```

```python
import os
from fastjob import FastJob

# Automatically uses correct database per environment
user_service = FastJob(database_url=os.environ["USER_SERVICE_DATABASE_URL"])
payment_service = FastJob(database_url=os.environ["PAYMENT_SERVICE_DATABASE_URL"])
```

**Complete service isolation achieved!** Each service has its own job queue, worker processes, and database - no cross-service interference possible.

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

When you need separate databases, create FastJob instances:

```python
from fastjob import FastJob

# Different services, different databases
user_service = FastJob(database_url="postgresql://localhost/users")
order_service = FastJob(database_url="postgresql://localhost/orders")

@user_service.job()
async def send_welcome_email(user_id: int):
    # User service job
    pass

@order_service.job()  
async def process_payment(order_id: int):
    # Order service job
    pass

# Same worker management pattern
if fastjob.is_dev_mode():
    await user_service.start_embedded_worker()
# Production: fastjob start --database-url="postgresql://localhost/users"
```

See [Instance API guide](docs/instance-api.md) for detailed examples.

### Which One Should You Use?

**Start with Global API** - it's simpler and works for 90% of apps.

**Use Instance-Based API** when you need separate databases (microservices, multi-tenant apps, etc.).

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

### Environment Variables (Simple)

Two settings you need to know about:

```bash
# Your database (required)
export FASTJOB_DATABASE_URL="postgresql://localhost/myapp"

# Development mode (optional, makes workers run in your app)
export FASTJOB_DEV_MODE=true
```

**That's it.** Everything else has sensible defaults.

### Configuration File (Even Simpler)

Create a `.env` file in your project root:

```bash
# .env
FASTJOB_DATABASE_URL=postgresql://localhost/myapp
FASTJOB_DEV_MODE=true
FASTJOB_RESULT_TTL=300
FASTJOB_LOG_LEVEL=INFO
```

FastJob automatically loads `.env` files - no extra setup needed!

### All Available Settings

```bash
FASTJOB_DATABASE_URL=postgresql://localhost/myapp    # Database connection (required)
FASTJOB_DEV_MODE=true                               # Enable embedded workers for development
FASTJOB_RESULT_TTL=300                              # Keep completed jobs for 5 minutes (0 = delete immediately)
FASTJOB_JOBS_MODULE=myapp.tasks                     # Where to find @job functions (default: auto-discover) 
FASTJOB_LOG_LEVEL=INFO                              # Logging level (DEBUG, INFO, WARNING, ERROR)
FASTJOB_DEFAULT_CONCURRENCY=4                       # Default worker concurrency
FASTJOB_WORKER_HEARTBEAT_INTERVAL=5.0               # Worker heartbeat interval in seconds
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

## Production Ready

FastJob is battle-tested with 373+ tests covering error handling, worker monitoring, connection management, and more.

For deployment guides (Docker, systemd, monitoring), see [production docs](docs/production.md).

## Migrating from Celery/RQ?

FastJob is simpler: no Redis/RabbitMQ needed, async-first, type-safe, and embedded dev workers.

See [migration guide](docs/migration.md) for detailed examples.

Need framework-specific examples? Check out the [integration guide](docs/integrations.md) for FastAPI, Django, and Flask.

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
