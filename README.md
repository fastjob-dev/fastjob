# FastJob

**A simple, reliable job queue for Python**

FastJob is a background job library I built for Python developers who want something that just works. It uses PostgreSQL for persistence and embraces Python's async/await syntax. Think of it as Sidekiq for Python, but designed from the ground up for async.

## Why FastJob?

I was tired of complicated job queues that required Redis clusters or had confusing APIs. FastJob is different:

- **Dead simple** - Decorate a function, call `enqueue()`, done
- **Uses PostgreSQL** - One less service to manage and monitor
- **Async native** - Built for modern Python 3.10+
- **Type safe** - Pydantic validation keeps your jobs clean
- **Great DX** - Embedded worker for dev, CLI for production

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

### Write some jobs

```python
import fastjob

@fastjob.job()
async def send_welcome_email(user_email: str, name: str):
    # Your email logic here
    print(f"Sending welcome email to {name} at {user_email}")

@fastjob.job(retries=5, queue="critical")
async def process_payment(order_id: int, amount: float):
    # Your payment processing logic
    print(f"Processing ${amount} for order {order_id}")
```

### Queue them up

```python
# Queue a job
job_id = await fastjob.enqueue(
    send_welcome_email,
    user_email="alice@example.com",
    name="Alice"
)

# Queue with priority (lower number = higher priority)
urgent_job = await fastjob.enqueue(
    process_payment,
    priority=1,
    order_id=12345,
    amount=99.99
)
```

### Process jobs

**For development:**
```python
# This runs jobs in your main process
fastjob.start_embedded_worker()
```

**For production:**
```bash
# This runs as a separate worker process
fastjob run-worker --concurrency 4
```

## Real-world example

Here's how I use FastJob in a typical web app:

```python
from fastapi import FastAPI
import fastjob

app = FastAPI()

@fastjob.job(retries=3)
async def resize_uploaded_image(user_id: int, image_path: str):
    # Resize image, upload to CDN, update database
    pass

@fastjob.job(queue="emails", retries=2)
async def send_notification(user_id: int, message: str):
    # Send push notification or email
    pass

@app.post("/upload-photo/")
async def upload_photo(user_id: int, image_data: bytes):
    # Save the raw image
    image_path = save_image(image_data)
    
    # Queue background processing
    await fastjob.enqueue(resize_uploaded_image, user_id=user_id, image_path=image_path)
    
    return {"status": "uploaded", "processing": "queued"}

@app.on_event("startup")
async def startup():
    if app.debug:
        fastjob.start_embedded_worker()  # For development

@app.on_event("shutdown")
async def shutdown():
    await fastjob.stop_embedded_worker()
```

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

## Configuration

FastJob is configured via environment variables:

```bash
# Required: Database connection
export FASTJOB_DATABASE_URL="postgresql://user:password@localhost/myapp"

# Optional: Where to find your job functions
export FASTJOB_JOBS_MODULE="myapp.jobs"

# Optional: Logging level
export FASTJOB_LOG_LEVEL="INFO"
```

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