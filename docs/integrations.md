# Framework Integration Guide

FastJob works great with all major Python web frameworks. Here's how to integrate it with your favorite framework.

## FastAPI (Recommended)

FastAPI and FastJob are a perfect match - both are async-first and modern.

### Global API Approach

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
    # Your background processing logic
    print(f"Processing file {file_id}")
    # Simulate work
    await asyncio.sleep(2)
    return {"file_id": file_id, "status": "processed"}

@app.post("/upload/")
async def upload_file(file_id: int):
    # Enqueue background job
    job_id = await fastjob.enqueue(process_upload, file_id=file_id)
    return {"status": "uploaded", "job_id": job_id}

@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    status = await fastjob.get_job_status(job_id)
    return {"job_id": job_id, "status": status}
```

### Instance-Based Approach (Multi-tenant)

Perfect for SaaS applications where each tenant needs isolated job processing:

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
    # Define tenant-specific job
    @fastjob_app.job()
    async def process_tenant_upload(file_id: int):
        print(f"Processing file {file_id} for tenant {tenant_id}")
        return {"tenant": tenant_id, "file_id": file_id}
    
    job_id = await fastjob_app.enqueue(process_tenant_upload, file_id=file_id)
    return {"status": "processing", "tenant": tenant_id, "job_id": job_id}

@app.on_event("shutdown")
async def shutdown():
    # Clean shutdown for all tenant instances
    for fastjob_app in tenant_jobs.values():
        await fastjob_app.close()
```

### Running the FastAPI App

Development:
```bash
FASTJOB_DEV_MODE=true uvicorn main:app --reload
# Jobs run embedded in your FastAPI process
```

Production:
```bash
# Start your FastAPI app
uvicorn main:app

# Start FastJob workers separately
fastjob start --concurrency 4
```

## Django

Django works great with FastJob. Since Django is primarily sync, you'll use `asyncio.run()` to call FastJob's async functions.

### Setup

```python
# settings.py
import fastjob
import os

# Configure FastJob
fastjob.configure(
    database_url=os.getenv("FASTJOB_DATABASE_URL", "postgresql://localhost/django_app")
)

# Optional: Start embedded worker in development
if fastjob.is_dev_mode():
    import asyncio
    asyncio.create_task(fastjob.start_embedded_worker())
```

### Define Jobs

```python
# jobs.py
import fastjob
import asyncio
from django.core.mail import send_mail
from django.contrib.auth.models import User

@fastjob.job(retries=3)
async def send_notification_email(user_id: int, subject: str, message: str):
    """Send notification email to user"""
    try:
        user = await asyncio.to_thread(User.objects.get, id=user_id)
        
        await asyncio.to_thread(
            send_mail,
            subject,
            message,
            'noreply@yourapp.com',
            [user.email]
        )
        
        return {"user_id": user_id, "status": "sent"}
    except User.DoesNotExist:
        return {"error": f"User {user_id} not found"}

@fastjob.job()
async def process_user_data(user_id: int, data: dict):
    """Process user data in background"""
    # Your processing logic here
    print(f"Processing data for user {user_id}: {data}")
    await asyncio.sleep(1)  # Simulate work
    return {"user_id": user_id, "processed": True}
```

### Use in Views

```python
# views.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import asyncio
import json
from .jobs import send_notification_email, process_user_data
import fastjob

@csrf_exempt
@require_http_methods(["POST"])
def send_notification(request):
    data = json.loads(request.body)
    user_id = data.get('user_id')
    subject = data.get('subject')
    message = data.get('message')
    
    # Enqueue the job
    job_id = asyncio.run(fastjob.enqueue(
        send_notification_email,
        user_id=user_id,
        subject=subject, 
        message=message
    ))
    
    return JsonResponse({
        "status": "queued",
        "job_id": job_id
    })

@csrf_exempt  
@require_http_methods(["POST"])
def process_data(request):
    data = json.loads(request.body)
    user_id = data.get('user_id')
    user_data = data.get('data', {})
    
    job_id = asyncio.run(fastjob.enqueue(
        process_user_data,
        user_id=user_id,
        data=user_data
    ))
    
    return JsonResponse({
        "status": "processing", 
        "job_id": job_id
    })

def job_status(request, job_id):
    status = asyncio.run(fastjob.get_job_status(job_id))
    return JsonResponse({
        "job_id": job_id,
        "status": status
    })
```

### Running Django + FastJob

Development:
```bash
FASTJOB_DEV_MODE=true python manage.py runserver
# Jobs run embedded in Django process
```

Production:
```bash
# Start Django
python manage.py runserver

# Start FastJob workers
fastjob start --concurrency 4
```

## Flask

Flask integration is straightforward. Like Django, you'll use `asyncio.run()` for async job functions.

### Global API Approach

```python
from flask import Flask, request, jsonify
import fastjob
import asyncio
import os

app = Flask(__name__)

# Configure FastJob at app startup
@app.before_first_request
def configure_fastjob():
    fastjob.configure(
        database_url=os.getenv("FASTJOB_DATABASE_URL", "postgresql://localhost/flask_app")
    )
    
    if fastjob.is_dev_mode():
        # Start embedded worker in background thread
        import threading
        def start_worker():
            asyncio.run(fastjob.start_embedded_worker())
        threading.Thread(target=start_worker, daemon=True).start()

@fastjob.job()
async def send_email(email: str, subject: str, body: str):
    """Send email in background"""
    print(f"Sending email to {email}: {subject}")
    # Your email sending logic here
    await asyncio.sleep(1)  # Simulate sending
    return {"email": email, "status": "sent"}

@fastjob.job(retries=3)
async def process_image(image_path: str, user_id: int):
    """Process uploaded image"""
    print(f"Processing image {image_path} for user {user_id}")
    # Your image processing logic here
    await asyncio.sleep(2)  # Simulate processing
    return {"image": image_path, "user_id": user_id, "status": "processed"}

@app.route('/send-email', methods=['POST'])
def trigger_email():
    data = request.get_json()
    
    job_id = asyncio.run(fastjob.enqueue(
        send_email,
        email=data['email'],
        subject=data['subject'],
        body=data['body']
    ))
    
    return jsonify({
        "status": "queued",
        "job_id": job_id
    })

@app.route('/process-image', methods=['POST'])
def trigger_image_processing():
    data = request.get_json()
    
    job_id = asyncio.run(fastjob.enqueue(
        process_image,
        image_path=data['image_path'],
        user_id=data['user_id']
    ))
    
    return jsonify({
        "status": "processing",
        "job_id": job_id
    })

@app.route('/job/<job_id>')
def get_job_status_route(job_id):
    status = asyncio.run(fastjob.get_job_status(job_id))
    return jsonify({
        "job_id": job_id,
        "status": status
    })
```

### Instance-Based Approach

```python
from flask import Flask, g, request, jsonify
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

@app.route('/process', methods=['POST'])
def process_data():
    fastjob_app = get_fastjob()
    data = request.get_json()
    
    @fastjob_app.job()
    async def background_task(data: dict):
        print(f"Processing: {data}")
        await asyncio.sleep(1)
        return {"processed": data}
    
    job_id = asyncio.run(fastjob_app.enqueue(background_task, data=data))
    return jsonify({"status": "queued", "job_id": job_id})
```

### Running Flask + FastJob

Development:
```bash
FASTJOB_DEV_MODE=true flask run
# Jobs run embedded in Flask process
```

Production:
```bash
# Start Flask app
flask run

# Start FastJob workers
fastjob start --concurrency 4
```

## General Tips

### Async/Sync Integration

When working with sync frameworks (Django, Flask), use these patterns:

```python
# In sync code, call async FastJob functions
import asyncio

# Enqueue jobs
job_id = asyncio.run(fastjob.enqueue(my_job, arg="value"))

# Check job status  
status = asyncio.run(fastjob.get_job_status(job_id))

# In async jobs, call sync Django/Flask code
@fastjob.job()
async def my_job(arg: str):
    # Call sync Django ORM
    result = await asyncio.to_thread(MyModel.objects.get, id=123)
    return result
```

### Error Handling

```python
@fastjob.job(retries=3)
async def reliable_job(data: dict):
    try:
        # Your job logic
        result = await process_data(data)
        return {"success": True, "result": result}
    except Exception as e:
        # Log the error
        print(f"Job failed: {e}")
        # Re-raise to trigger retry
        raise
```

### Testing

```python
# In tests, disable embedded workers
import fastjob
from fastjob.testing import disable_plugins, no_plugins

# Disable for entire test
disable_plugins()

# Or use context manager
def test_job_enqueue():
    with no_plugins():
        job_id = await fastjob.enqueue(my_job, data="test")
        assert job_id is not None
```

### Monitoring

```bash
# Check job status
fastjob status --jobs

# Monitor workers
fastjob workers

# View queue stats
fastjob status --verbose
```

That's it! FastJob integrates cleanly with any Python web framework. The key is using the right API pattern (Global vs Instance) for your architecture and handling the async/sync boundary appropriately.