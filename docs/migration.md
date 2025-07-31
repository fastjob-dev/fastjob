# Migration Guide

Switching from other job queues to FastJob? Here's how to migrate from the most popular options.

## From Celery

Celery is powerful but complex. FastJob gives you the same reliability with much less setup.

### Before: Celery Setup

```python
# Celery setup (complex)
from celery import Celery
from kombu import Queue

app = Celery('myapp')
app.config_from_object({
    'broker_url': 'redis://localhost:6379/0',
    'result_backend': 'redis://localhost:6379/0',
    'task_serializer': 'json',
    'accept_content': ['json'],
    'result_serializer': 'json',
    'timezone': 'UTC',
    'enable_utc': True,
    'task_routes': {
        'myapp.tasks.send_email': {'queue': 'emails'},
        'myapp.tasks.process_payment': {'queue': 'payments'},
    }
})

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def send_email(self, user_email, subject, body):
    try:
        # Your email logic here
        import smtplib
        # ... email sending code
        return {"status": "sent", "email": user_email}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5})
def process_payment(self, order_id, amount):
    try:
        # Payment processing logic
        # ... payment code
        return {"order_id": order_id, "amount": amount}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)

# Separate worker process required
# celery -A myapp worker --loglevel=info --queues=emails,payments
```

### After: FastJob Setup

```python
# FastJob setup (simple)
import fastjob

@fastjob.job(retries=3, queue="emails")
async def send_email(user_email: str, subject: str, body: str):
    # Your email logic here (now with type hints!)
    import aiosmtplib
    # ... async email sending code
    return {"status": "sent", "email": user_email}

@fastjob.job(retries=5, queue="payments")
async def process_payment(order_id: int, amount: float):
    # Payment processing logic (type-safe!)
    # ... async payment code
    return {"order_id": order_id, "amount": amount}

# Worker management - same code, different environments
if fastjob.is_dev_mode():
    fastjob.start_embedded_worker()
# Production: fastjob start --queues emails,payments
```

### Key Migration Benefits

- ✅ **No Redis/RabbitMQ** - uses your existing PostgreSQL
- ✅ **Type safety** - Pydantic validation built-in, no more mysterious failures
- ✅ **Embedded development mode** - no separate worker process needed locally
- ✅ **Modern async** - no sync/async complexity, works great with FastAPI
- ✅ **Simpler configuration** - just environment variables, no complex config objects

### Migration Steps

1. **Install FastJob:**
   ```bash
   pip install fastjob
   ```

2. **Setup database:**
   ```bash
   export FASTJOB_DATABASE_URL="postgresql://localhost/myapp"
   fastjob setup
   ```

3. **Convert tasks to jobs:**
   ```python
   # Celery
   @app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
   def my_task(self, arg1, arg2):
       # ...
   
   # FastJob
   @fastjob.job(retries=3)
   async def my_job(arg1: str, arg2: int):
       # ... (now async and type-safe!)
   ```

4. **Update enqueueing:**
   ```python
   # Celery
   my_task.delay(arg1="hello", arg2=42)
   
   # FastJob
   await fastjob.enqueue(my_job, arg1="hello", arg2=42)
   ```

5. **Update worker startup:**
   ```python
   # Development
   if fastjob.is_dev_mode():
       fastjob.start_embedded_worker()
   
   # Production
   # fastjob start --concurrency 4 --queues emails,payments
   ```

### Celery Features → FastJob Equivalents

| Celery | FastJob |
|--------|---------|
| `@app.task(bind=True)` | `@fastjob.job()` |
| `task.delay()` | `await fastjob.enqueue()` |
| `task.apply_async()` | `await fastjob.schedule()` |
| `self.retry()` | Automatic with `retries=N` |
| `task.AsyncResult()` | `await fastjob.get_job_status()` |
| Beat scheduler | FastJob Pro |
| Flower monitoring | FastJob Pro dashboard |

## From RQ (Redis Queue)

RQ is simpler than Celery but sync-only. FastJob gives you async support with the same simplicity.

### Before: RQ Setup

```python
# RQ setup (sync only)
from rq import Queue, Worker
from redis import Redis
import time

redis_conn = Redis(host='localhost', port=6379, db=0)
q = Queue('default', connection=redis_conn)

def send_email(user_email, subject, body):
    """Send email (sync function only)"""
    print(f"Sending email to {user_email}")
    time.sleep(2)  # Simulate email sending
    return {"status": "sent", "email": user_email}

def process_data(data):
    """Process data (sync function only)"""
    print(f"Processing: {data}")
    time.sleep(1)  # Simulate processing
    return {"processed": data}

# Enqueue jobs
job1 = q.enqueue(send_email, "user@example.com", "Hello", "Welcome!")
job2 = q.enqueue(process_data, {"key": "value"})

# Worker process required
# rq worker --url redis://localhost:6379
```

### After: FastJob Setup

```python
# FastJob setup (async-first)
import fastjob
import asyncio

@fastjob.job()
async def send_email(user_email: str, subject: str, body: str):
    """Send email (async with type validation)"""
    print(f"Sending email to {user_email}")
    await asyncio.sleep(2)  # Async email sending
    return {"status": "sent", "email": user_email}

@fastjob.job()
async def process_data(data: dict):
    """Process data (async with type validation)"""
    print(f"Processing: {data}")
    await asyncio.sleep(1)  # Async processing
    return {"processed": data}

# Enqueue jobs (same simplicity, now async)
job1_id = await fastjob.enqueue(send_email, "user@example.com", "Hello", "Welcome!")
job2_id = await fastjob.enqueue(process_data, {"key": "value"})

# Worker management
if fastjob.is_dev_mode():
    fastjob.start_embedded_worker()
# Production: fastjob start
```

### Migration Benefits

- ✅ **Async support** - RQ is sync-only, FastJob is async-first
- ✅ **No Redis dependency** - one less service to manage
- ✅ **Type validation** - Pydantic models catch errors early
- ✅ **Better development experience** - embedded worker for local dev
- ✅ **Same simplicity** - RQ's ease of use with modern async support

### Migration Steps

1. **Install FastJob:**
   ```bash
   pip install fastjob
   ```

2. **Setup database:**
   ```bash
   export FASTJOB_DATABASE_URL="postgresql://localhost/myapp"
   fastjob setup
   ```

3. **Convert functions to async jobs:**
   ```python
   # RQ
   def my_function(arg1, arg2):
       # sync code
       return result
   
   # FastJob
   @fastjob.job()
   async def my_job(arg1: str, arg2: int):
       # async code with types
       return result
   ```

4. **Update enqueueing:**
   ```python
   # RQ
   job = queue.enqueue(my_function, arg1="hello", arg2=42)
   
   # FastJob
   job_id = await fastjob.enqueue(my_job, arg1="hello", arg2=42)
   ```

## From Dramatiq

Dramatiq is a good alternative to Celery. FastJob offers similar features with PostgreSQL instead of Redis.

### Before: Dramatiq Setup

```python
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.results import Results
from dramatiq.results.backends import RedisBackend

redis_broker = RedisBroker(host="localhost", port=6379, db=0)
result_backend = RedisBackend(host="localhost", port=6379, db=1)
redis_broker.add_middleware(Results(backend=result_backend))
dramatiq.set_broker(redis_broker)

@dramatiq.actor(max_retries=3, queue_name="emails")
def send_email(user_email, subject, body):
    # Email sending logic
    return {"status": "sent", "email": user_email}

@dramatiq.actor(max_retries=5, time_limit=300000)  # 5 minutes
def process_payment(order_id, amount):
    # Payment processing logic
    return {"order_id": order_id, "amount": amount}

# Enqueue
send_email.send(user_email="user@example.com", subject="Hello", body="Welcome!")

# Worker: dramatiq workers
```

### After: FastJob Setup

```python
import fastjob

@fastjob.job(retries=3, queue="emails")
async def send_email(user_email: str, subject: str, body: str):
    # Async email sending logic with type safety
    return {"status": "sent", "email": user_email}

@fastjob.job(retries=5)
async def process_payment(order_id: int, amount: float):
    # Async payment processing logic with type safety
    return {"order_id": order_id, "amount": amount}

# Enqueue
await fastjob.enqueue(send_email, user_email="user@example.com", subject="Hello", body="Welcome!")

# Worker management
if fastjob.is_dev_mode():
    fastjob.start_embedded_worker()
# Production: fastjob start
```

## From Huey

Huey is lightweight and simple. FastJob provides similar simplicity with better async support.

### Before: Huey Setup

```python
from huey import RedisHuey
from datetime import datetime, timedelta

huey = RedisHuey('my-app', host='localhost', port=6379)

@huey.task(retries=3)
def send_email(user_email, subject):
    # Email logic
    return {"sent": user_email}

@huey.periodic_task(crontab(minute='0'))
def cleanup_old_data():
    # Cleanup logic
    pass

# Enqueue
send_email(user_email="user@example.com", subject="Hello")

# Worker: huey_consumer.py my_app.huey
```

### After: FastJob Setup

```python
import fastjob

@fastjob.job(retries=3)
async def send_email(user_email: str, subject: str):
    # Async email logic with type hints
    return {"sent": user_email}

# For periodic tasks, use FastJob Pro
# @fastjob.schedule("0 * * * *")  # Every hour
# async def cleanup_old_data():
#     # Async cleanup logic
#     pass

# Enqueue
await fastjob.enqueue(send_email, user_email="user@example.com", subject="Hello")

# Worker management
if fastjob.is_dev_mode():
    fastjob.start_embedded_worker()
```

## General Migration Tips

### 1. Gradual Migration

You can run FastJob alongside your existing queue system during migration:

```python
# Keep both during transition
import fastjob
from your_old_queue import old_queue

# New jobs use FastJob
@fastjob.job()
async def new_job(data: dict):
    return await process_data_async(data)

# Old jobs stay the same temporarily
def old_job(data):
    return process_data_sync(data)

# Gradually move jobs over
```

### 2. Testing Your Migration

```python
# Test both old and new implementations
async def test_migration():
    # Test new FastJob implementation
    job_id = await fastjob.enqueue(new_job, data={"test": True})
    result = await fastjob.get_job_status(job_id)
    assert result["status"] == "completed"
```

### 3. Performance Comparison

FastJob vs Redis-based queues:

- **Throughput**: Comparable for most workloads
- **Latency**: PostgreSQL LISTEN/NOTIFY gives near-instant job pickup
- **Reliability**: PostgreSQL's ACID guarantees vs Redis's memory-first approach
- **Operational complexity**: Much simpler - one less service to manage

### 4. Common Patterns

**Batch processing:**
```python
# Old way (various patterns)
for item in items:
    queue.enqueue(process_item, item)

# FastJob way
@fastjob.job()
async def process_batch(items: list):
    results = []
    for item in items:
        result = await process_item(item)
        results.append(result)
    return results

await fastjob.enqueue(process_batch, items=large_list)
```

**Workflows:**
```python
# Chain jobs together
@fastjob.job()
async def step_1(data: dict):
    result = await process_step_1(data)
    # Enqueue next step
    await fastjob.enqueue(step_2, result=result)
    return result

@fastjob.job()
async def step_2(result: dict):
    return await process_step_2(result)
```

### 5. Monitoring Migration

```bash
# Monitor job processing during migration
fastjob status --verbose --jobs

# Check for failed jobs
fastjob status | grep -i failed

# Monitor worker health
fastjob workers
```

## Need Help?

- Check the [integration guide](integrations.md) for framework-specific examples
- See [production deployment](production.md) for scaling guidance
- Review the main README for quickstart examples

Migration questions? Open an issue on GitHub or email abhinav@apiclabs.com.