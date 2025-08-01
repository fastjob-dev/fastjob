# Instance API Guide

The Instance API gives you full control over multiple isolated FastJob instances. Perfect for microservices, multi-tenant applications, or any scenario where you need separate job queues.

## When to Use Instance API

**Use the Instance API when:**
- Building microservices with separate databases per service
- Creating multi-tenant applications with tenant isolation
- Need different configurations for different parts of your app
- Building libraries that embed FastJob functionality
- Testing scenarios requiring complete isolation

**Stick with Global API when:**
- Single database application
- Simple configuration needs
- Just getting started
- Following typical web framework patterns

## Basic Usage

### Creating Instances

```python
from fastjob import FastJob

# Basic instance
app = FastJob(database_url="postgresql://localhost/myapp")

# With custom configuration
app = FastJob(
    database_url="postgresql://localhost/myapp",
    default_concurrency=4,
    result_ttl=600,  # 10 minutes
    db_pool_min_size=5,
    db_pool_max_size=20
)
```

### Defining Jobs

Jobs are bound to specific instances:

```python
@app.job()
async def send_email(to: str, subject: str):
    print(f"Sending email to {to}: {subject}")
    return {"sent": True, "to": to}

@app.job(retries=3, queue="payments")
async def process_payment(order_id: int, amount: float):
    print(f"Processing ${amount} for order {order_id}")
    return {"order_id": order_id, "amount": amount}
```

### Enqueueing Jobs

```python
# Enqueue jobs on the instance
job_id = await app.enqueue(send_email, to="user@example.com", subject="Welcome!")

# Schedule jobs
from datetime import datetime, timedelta
later_job = await app.schedule(
    process_payment,
    run_in=timedelta(hours=1),
    order_id=12345,
    amount=99.99
)
```

### Worker Management

Development mode:
```python
if fastjob.is_dev_mode():
    await app.start_embedded_worker()
```

Production mode:
```bash
fastjob start --database-url="postgresql://localhost/myapp" --concurrency 4
```

### Cleanup

Always close instances when done:
```python
# Important: Clean up connections
await app.close()
```

## Microservices Architecture

Perfect pattern for microservices where each service has its own database:

```python
from fastjob import FastJob
import asyncio

# User Service
user_service = FastJob(
    database_url="postgresql://localhost/user_service",
    default_concurrency=2
)

@user_service.job(retries=3, queue="user_emails")
async def send_welcome_email(user_id: int, email: str):
    print(f"Sending welcome email to user {user_id}: {email}")
    # Email sending logic
    await asyncio.sleep(1)
    return {"user_id": user_id, "email_sent": True, "timestamp": datetime.now()}

@user_service.job(queue="user_profile")
async def update_user_profile(user_id: int, profile_data: dict):
    print(f"Updating profile for user {user_id}")
    # Profile update logic
    return {"user_id": user_id, "updated": True}

# Order Service  
order_service = FastJob(
    database_url="postgresql://localhost/order_service",
    default_concurrency=4,
    result_ttl=3600  # Keep results longer for orders
)

@order_service.job(retries=5, queue="payments")
async def process_payment(order_id: int, amount: float, payment_method: str):
    print(f"Processing ${amount} payment for order {order_id} via {payment_method}")
    # Payment processing logic
    await asyncio.sleep(2)
    return {
        "order_id": order_id, 
        "amount": amount, 
        "status": "processed",
        "payment_method": payment_method
    }

@order_service.job(queue="fulfillment")
async def ship_order(order_id: int, shipping_address: dict):
    print(f"Shipping order {order_id} to {shipping_address}")
    # Shipping logic
    return {"order_id": order_id, "shipped": True}

# Notification Service
notification_service = FastJob(
    database_url="postgresql://localhost/notifications",
    default_concurrency=1  # Rate-limited notifications
)

@notification_service.job(retries=2, queue="sms")
async def send_sms(phone: str, message: str):
    print(f"Sending SMS to {phone}: {message}")
    # SMS sending logic
    return {"phone": phone, "sent": True}

@notification_service.job(queue="push")
async def send_push_notification(device_token: str, title: str, body: str):
    print(f"Sending push notification: {title}")
    # Push notification logic
    return {"device_token": device_token, "sent": True}
```

### Service Usage

```python
# User signup workflow
async def handle_user_signup(user_id: int, email: str, phone: str):
    # Send welcome email via user service
    email_job = await user_service.enqueue(
        send_welcome_email, 
        user_id=user_id, 
        email=email
    )
    
    # Send SMS notification via notification service
    sms_job = await notification_service.enqueue(
        send_sms,
        phone=phone,
        message=f"Welcome! Your account {user_id} is ready."
    )
    
    return {"email_job": email_job, "sms_job": sms_job}

# Order processing workflow
async def handle_new_order(order_id: int, amount: float, payment_method: str):
    # Process payment via order service
    payment_job = await order_service.enqueue(
        process_payment,
        order_id=order_id,
        amount=amount,
        payment_method=payment_method
    )
    
    return {"payment_job": payment_job}
```

### Worker Management for Microservices

Development - embedded workers:
```python
async def start_dev_workers():
    if fastjob.is_dev_mode():
        await asyncio.gather(
            user_service.start_embedded_worker(concurrency=2, queues=["user_emails", "user_profile"]),
            order_service.start_embedded_worker(concurrency=4, queues=["payments", "fulfillment"]),
            notification_service.start_embedded_worker(concurrency=1, queues=["sms", "push"])
        )
```

Production - separate CLI workers:
```bash
# User service workers
fastjob start --database-url="postgresql://localhost/user_service" --concurrency 2 --queues user_emails,user_profile

# Order service workers  
fastjob start --database-url="postgresql://localhost/order_service" --concurrency 4 --queues payments,fulfillment

# Notification service workers
fastjob start --database-url="postgresql://localhost/notifications" --concurrency 1 --queues sms,push
```

### Service Cleanup

```python
async def shutdown_services():
    """Clean shutdown of all services"""
    await asyncio.gather(
        user_service.close(),
        order_service.close(),
        notification_service.close()
    )
```

## Multi-Tenant Applications

Each tenant gets isolated job processing:

```python
from fastjob import FastJob
from typing import Dict

class TenantJobManager:
    def __init__(self):
        self.tenant_instances: Dict[str, FastJob] = {}
    
    def get_tenant_instance(self, tenant_id: str) -> FastJob:
        """Get or create FastJob instance for tenant"""
        if tenant_id not in self.tenant_instances:
            self.tenant_instances[tenant_id] = FastJob(
                database_url=f"postgresql://localhost/tenant_{tenant_id}",
                default_concurrency=2,
                result_ttl=1800  # 30 minutes
            )
        return self.tenant_instances[tenant_id]
    
    def define_tenant_jobs(self, tenant_instance: FastJob):
        """Define jobs for a tenant instance"""
        
        @tenant_instance.job(retries=3)
        async def send_tenant_email(user_id: int, email: str, template: str):
            print(f"Sending {template} email to {email} for user {user_id}")
            # Tenant-specific email logic with custom branding
            return {"user_id": user_id, "email": email, "template": template}
        
        @tenant_instance.job(queue="reports")
        async def generate_tenant_report(report_type: str, params: dict):
            print(f"Generating {report_type} report with params: {params}")
            # Tenant-specific reporting logic
            return {"report_type": report_type, "generated": True}
        
        return tenant_instance
    
    async def enqueue_for_tenant(self, tenant_id: str, job_func, **kwargs):
        """Enqueue job for specific tenant"""
        tenant_instance = self.get_tenant_instance(tenant_id)
        self.define_tenant_jobs(tenant_instance)  # Ensure jobs are defined
        return await tenant_instance.enqueue(job_func, **kwargs)
    
    async def close_all(self):
        """Close all tenant instances"""
        for instance in self.tenant_instances.values():
            await instance.close()
        self.tenant_instances.clear()

# Usage
tenant_manager = TenantJobManager()

async def handle_tenant_action(tenant_id: str, user_id: int, email: str):
    tenant_instance = tenant_manager.get_tenant_instance(tenant_id)
    tenant_manager.define_tenant_jobs(tenant_instance)
    
    # Enqueue job for this specific tenant
    job_id = await tenant_instance.enqueue(
        send_tenant_email,  # This will be bound to the tenant's instance
        user_id=user_id,
        email=email,
        template="welcome"
    )
    
    return {"tenant_id": tenant_id, "job_id": job_id}
```

### Multi-Tenant Workers

Each tenant can have dedicated workers:

```bash
# Tenant A workers
fastjob start --database-url="postgresql://localhost/tenant_a" --concurrency 2

# Tenant B workers  
fastjob start --database-url="postgresql://localhost/tenant_b" --concurrency 2

# Or shared workers processing multiple tenants
fastjob start --database-url="postgresql://localhost/tenant_a" --concurrency 1 &
fastjob start --database-url="postgresql://localhost/tenant_b" --concurrency 1 &
```

## Configuration Management

### Instance Configuration

```python
from fastjob import FastJob

# Development configuration
dev_app = FastJob(
    database_url="postgresql://localhost/dev_db",
    default_concurrency=1,
    result_ttl=60,  # Short TTL for development
    db_pool_min_size=1,
    db_pool_max_size=3
)

# Production configuration
prod_app = FastJob(
    database_url="postgresql://prod-server/prod_db",
    default_concurrency=8,
    result_ttl=3600,  # 1 hour TTL for production
    db_pool_min_size=5,
    db_pool_max_size=20
)
```

### Environment-Based Configuration

```python
import os
from fastjob import FastJob

def create_app_instance(env: str = "development") -> FastJob:
    """Create FastJob instance based on environment"""
    
    if env == "production":
        return FastJob(
            database_url=os.getenv("PROD_DATABASE_URL"),
            default_concurrency=int(os.getenv("PROD_CONCURRENCY", "8")),
            result_ttl=int(os.getenv("PROD_RESULT_TTL", "3600")),
            db_pool_max_size=int(os.getenv("PROD_POOL_SIZE", "20"))
        )
    elif env == "staging":
        return FastJob(
            database_url=os.getenv("STAGING_DATABASE_URL"),
            default_concurrency=int(os.getenv("STAGING_CONCURRENCY", "4")),
            result_ttl=int(os.getenv("STAGING_RESULT_TTL", "1800"))
        )
    else:  # development
        return FastJob(
            database_url=os.getenv("DEV_DATABASE_URL", "postgresql://localhost/dev_db"),
            default_concurrency=1,
            result_ttl=60
        )

# Usage
app = create_app_instance(os.getenv("ENVIRONMENT", "development"))
```

## Testing with Instance API

Instance API provides excellent test isolation:

```python
import pytest
from fastjob import FastJob

@pytest.fixture
async def test_app():
    """Create isolated FastJob instance for testing"""
    app = FastJob(database_url="postgresql://localhost/test_db")
    
    # Define test jobs
    @app.job()
    async def test_job(data: str):
        return {"processed": data}
    
    yield app
    
    # Cleanup
    await app.close()

@pytest.mark.asyncio
async def test_job_processing(test_app):
    """Test job processing in isolation"""
    
    # Enqueue job
    job_id = await test_app.enqueue(test_job, data="test_data")
    
    # Process job
    await test_app.run_worker(run_once=True)
    
    # Check result
    status = await test_app.get_job_status(job_id)
    assert status["status"] == "completed"
    assert status["result"]["processed"] == "test_data"

@pytest.fixture
async def multi_tenant_test():
    """Test multiple tenant instances"""
    tenant_a = FastJob(database_url="postgresql://localhost/test_tenant_a")
    tenant_b = FastJob(database_url="postgresql://localhost/test_tenant_b")
    
    @tenant_a.job()
    async def tenant_a_job(data: str):
        return {"tenant": "A", "data": data}
    
    @tenant_b.job()
    async def tenant_b_job(data: str):
        return {"tenant": "B", "data": data}
    
    yield {"tenant_a": tenant_a, "tenant_b": tenant_b}
    
    # Cleanup
    await tenant_a.close()
    await tenant_b.close()
```

## Advanced Patterns

### Cross-Service Communication

```python
# Service A enqueues job in Service B
async def cross_service_workflow():
    # Process in Service A
    result_a = await service_a.enqueue(process_data_a, data="input")
    
    # Wait for completion (optional)
    while True:
        status = await service_a.get_job_status(result_a)
        if status["status"] == "completed":
            break
        await asyncio.sleep(0.1)
    
    # Use result in Service B
    result_data = status["result"]
    result_b = await service_b.enqueue(process_data_b, data=result_data)
    
    return {"service_a": result_a, "service_b": result_b}
```

### Dynamic Instance Creation

```python
from fastjob import FastJob
import asyncio

class DynamicJobManager:
    def __init__(self):
        self.instances = {}
        self.cleanup_tasks = {}
    
    async def get_or_create_instance(self, key: str, database_url: str) -> FastJob:
        """Get existing instance or create new one"""
        if key not in self.instances:
            self.instances[key] = FastJob(database_url=database_url)
            
            # Auto-cleanup after inactivity
            self.cleanup_tasks[key] = asyncio.create_task(
                self._schedule_cleanup(key, delay=300)  # 5 minutes
            )
        
        return self.instances[key]
    
    async def _schedule_cleanup(self, key: str, delay: int):
        """Clean up instance after delay"""
        await asyncio.sleep(delay)
        if key in self.instances:
            await self.instances[key].close()
            del self.instances[key]
            del self.cleanup_tasks[key]
    
    async def cleanup_all(self):
        """Clean up all instances"""
        for task in self.cleanup_tasks.values():
            task.cancel()
        
        for instance in self.instances.values():
            await instance.close()
        
        self.instances.clear()
        self.cleanup_tasks.clear()
```

## Best Practices

### 1. Resource Management

Always close instances:
```python
try:
    # Use FastJob instance
    result = await app.enqueue(my_job, data="test")
finally:
    # Always clean up
    await app.close()
```

### 2. Configuration Management

Use factories for consistent configuration:
```python
def create_service_instance(service_name: str, env: str = "production") -> FastJob:
    """Factory for creating service instances"""
    base_config = {
        "default_concurrency": 4,
        "result_ttl": 1800,
        "db_pool_min_size": 2,
        "db_pool_max_size": 10
    }
    
    if env == "development":
        base_config.update({
            "default_concurrency": 1,
            "result_ttl": 60,
            "db_pool_max_size": 3
        })
    
    return FastJob(
        database_url=f"postgresql://localhost/{service_name}_{env}",
        **base_config
    )
```

### 3. Error Handling

Handle instance initialization errors:
```python
async def safe_create_instance(database_url: str) -> FastJob:
    """Safely create FastJob instance with error handling"""
    try:
        app = FastJob(database_url=database_url)
        # Test connection
        await app.get_pool()
        return app
    except Exception as e:
        print(f"Failed to create FastJob instance: {e}")
        raise
```

### 4. Monitoring

Monitor each instance separately:
```python
async def monitor_instances(instances: Dict[str, FastJob]):
    """Monitor multiple FastJob instances"""
    for name, instance in instances.items():
        try:
            stats = await instance.get_queue_stats()
            print(f"{name}: {stats}")
        except Exception as e:
            print(f"Error monitoring {name}: {e}")
```

The Instance API gives you complete control over FastJob behavior. Use it when you need isolation, custom configuration, or multiple databases - but remember to keep it simple with the Global API for most use cases!