"""
Instance API Example - Multi-Database Job Processing

FastJob's Instance API lets you:
- Use multiple databases in the same app
- Keep jobs isolated by service, tenant, or environment
- Scale beyond a single job queue

Use Instance API when you need:
- Microservices with separate job queues
- Multi-tenant apps with data isolation
- Different job rules per service
- Independent scaling per service

Stick with Global API when you have:
- Single app with one job queue
- Simple background jobs
- Just getting started
"""

import asyncio
import os
from datetime import datetime
from pydantic import BaseModel

import fastjob
from fastjob import FastJob


# Job models (shared across all instances)
class UserData(BaseModel):
    user_id: str
    email: str
    name: str


class PaymentData(BaseModel):
    payment_id: str
    amount: float
    currency: str = "USD"


class AnalyticsData(BaseModel):
    event_name: str
    user_id: str
    properties: dict


# ========================================
# GLOBAL API APPROACH (single database)
# ========================================

@fastjob.job(queue="users")
async def global_process_user_signup(user_id: str, email: str, name: str) -> dict:
    """Process user signup using Global API."""
    print(f"[GLOBAL] Processing user signup: {email}")
    
    # Simulate user processing
    await asyncio.sleep(0.5)
    
    return {
        "user_id": user_id,
        "status": "processed",
        "processed_at": datetime.now().isoformat()
    }


@fastjob.job(queue="payments", priority=1)
async def global_process_payment(payment_id: str, amount: float) -> dict:
    """Process payment using Global API."""
    print(f"[GLOBAL] Processing payment: ${amount}")
    
    # Simulate payment processing
    await asyncio.sleep(1.0)
    
    return {
        "payment_id": payment_id,
        "amount": amount,
        "status": "completed",
        "processed_at": datetime.now().isoformat()
    }


# ========================================
# INSTANCE API APPROACH (multiple databases)
# ========================================

# Create separate FastJob instances for different services
user_service = FastJob(
    database_url=os.environ.get("USER_SERVICE_DATABASE_URL", "postgresql://localhost/user_service"),
    service_name="user_service"
)

payment_service = FastJob(
    database_url=os.environ.get("PAYMENT_SERVICE_DATABASE_URL", "postgresql://localhost/payment_service"),
    service_name="payment_service"
)

analytics_service = FastJob(
    database_url=os.environ.get("ANALYTICS_DATABASE_URL", "postgresql://localhost/analytics_service"),
    service_name="analytics_service"
)


# Register jobs with specific instances
@user_service.job(queue="signups", retries=3, args_model=UserData)
async def instance_process_user_signup(user_id: str, email: str, name: str) -> dict:
    """Process user signup using Instance API."""
    print(f"[USER_SERVICE] Processing user signup: {email}")
    
    # Simulate user processing with validation
    await asyncio.sleep(0.5)
    
    # This job only has access to user service database
    result = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "service": "user_service"
    }
    
    print(f"[USER_SERVICE] User created: {user_id}")
    return result


@payment_service.job(queue="transactions", priority=1, retries=5, args_model=PaymentData)
async def instance_process_payment(payment_id: str, amount: float, currency: str = "USD") -> dict:
    """Process payment using Instance API."""
    print(f"[PAYMENT_SERVICE] Processing payment: {amount} {currency}")
    
    # Simulate payment processing
    await asyncio.sleep(1.0)
    
    # This job only has access to payment service database
    result = {
        "payment_id": payment_id,
        "amount": amount,
        "currency": currency,
        "status": "completed",
        "processed_at": datetime.now().isoformat(),
        "service": "payment_service"
    }
    
    print(f"[PAYMENT_SERVICE] Payment completed: {payment_id}")
    return result


@analytics_service.job(queue="events", priority=5, args_model=AnalyticsData)
async def instance_track_event(event_name: str, user_id: str, properties: dict) -> dict:
    """Track analytics event using Instance API."""
    print(f"[ANALYTICS_SERVICE] Tracking event: {event_name} for user {user_id}")
    
    # Simulate analytics processing
    await asyncio.sleep(0.2)
    
    # This job only has access to analytics database
    result = {
        "event_name": event_name,
        "user_id": user_id,
        "properties": properties,
        "tracked_at": datetime.now().isoformat(),
        "service": "analytics_service"
    }
    
    print(f"[ANALYTICS_SERVICE] Event tracked: {event_name}")
    return result


# Cross-service job coordination using Instance API
@user_service.job()
async def instance_user_signup_workflow(user_id: str, email: str, name: str) -> dict:
    """Orchestrate user signup across multiple services."""
    print(f"[WORKFLOW] Starting signup workflow for: {email}")
    
    # Process user in user service (this instance)
    user_result = await user_service.enqueue(
        instance_process_user_signup,
        user_id=user_id,
        email=email,
        name=name
    )
    
    # Track signup event in analytics service (different instance)
    analytics_result = await analytics_service.enqueue(
        instance_track_event,
        event_name="user_signup",
        user_id=user_id,
        properties={"email": email, "source": "workflow"}
    )
    
    return {
        "workflow_id": f"signup_{user_id}",
        "user_job": user_result,
        "analytics_job": analytics_result,
        "status": "initiated"
    }


async def demonstrate_global_api():
    """Demonstrate Global API usage."""
    print("\n" + "="*60)
    print("GLOBAL API DEMONSTRATION")
    print("="*60)
    print("Using single database with multiple queues")
    
    # Start embedded worker for Global API
    print("\nStarting Global API embedded worker...")
    fastjob.start_embedded_worker()
    
    try:
        # Enqueue jobs using Global API
        print("\n1. Enqueuing user signup (Global API)...")
        user_job_id = await fastjob.enqueue(
            global_process_user_signup,
            user_id="user_123",
            email="user@example.com", 
            name="John Doe"
        )
        print(f"   User job ID: {user_job_id}")
        
        print("\n2. Enqueuing payment (Global API)...")
        payment_job_id = await fastjob.enqueue(
            global_process_payment,
            payment_id="pay_456",
            amount=99.99
        )
        print(f"   Payment job ID: {payment_job_id}")
        
        # Wait for jobs to process
        print("\n⏳ Processing jobs...")
        await asyncio.sleep(3)
        
    finally:
        print("\nStopping Global API embedded worker...")
        await fastjob.stop_embedded_worker()


async def demonstrate_instance_api():
    """Demonstrate Instance API usage with multiple services."""
    print("\n" + "="*60)
    print("INSTANCE API DEMONSTRATION")
    print("="*60)
    print("Using separate databases for different services")
    
    # Start embedded workers for each service
    print("\nStarting Instance API embedded workers...")
    user_service.start_embedded_worker()
    payment_service.start_embedded_worker()
    analytics_service.start_embedded_worker()
    
    try:
        # Demonstrate individual service jobs
        print("\n1. Enqueuing user signup (User Service)...")
        user_job_id = await user_service.enqueue(
            instance_process_user_signup,
            user_id="user_789",
            email="jane@example.com",
            name="Jane Smith"
        )
        print(f"   User service job ID: {user_job_id}")
        
        print("\n2. Enqueuing payment (Payment Service)...")
        payment_job_id = await payment_service.enqueue(
            instance_process_payment,
            payment_id="pay_789",
            amount=149.99,
            currency="USD"
        )
        print(f"   Payment service job ID: {payment_job_id}")
        
        print("\n3. Enqueuing analytics event (Analytics Service)...")
        analytics_job_id = await analytics_service.enqueue(
            instance_track_event,
            event_name="page_view",
            user_id="user_789",
            properties={"page": "/dashboard", "duration": 30}
        )
        print(f"   Analytics service job ID: {analytics_job_id}")
        
        # Demonstrate cross-service workflow
        print("\n4. Enqueuing cross-service workflow...")
        workflow_job_id = await user_service.enqueue(
            instance_user_signup_workflow,
            user_id="user_999",
            email="workflow@example.com",
            name="Workflow User"
        )
        print(f"   Workflow job ID: {workflow_job_id}")
        
        # Wait for jobs to process
        print("\n⏳ Processing jobs across all services...")
        await asyncio.sleep(5)
        
        # Show service status
        print("\n📊 Service Status:")
        user_status = await user_service.get_queue_status()
        payment_status = await payment_service.get_queue_status()
        analytics_status = await analytics_service.get_queue_status()
        
        print(f"   User Service: {user_status}")
        print(f"   Payment Service: {payment_status}")
        print(f"   Analytics Service: {analytics_status}")
        
    finally:
        print("\nStopping Instance API embedded workers...")
        await user_service.stop_embedded_worker()
        await payment_service.stop_embedded_worker()
        await analytics_service.stop_embedded_worker()
        
        # Close database connections
        await user_service.close()
        await payment_service.close()
        await analytics_service.close()


async def main():
    """
    Main example function demonstrating both Global and Instance API approaches.
    """
    print("🚀 FastJob Instance API Example")
    print("Demonstrating Global API vs Instance API patterns")
    
    # Show when to use each approach
    print("\n📖 API COMPARISON:")
    print("Global API: Single database, simple setup, great for getting started")
    print("Instance API: Multiple databases, service isolation, production microservices")
    
    # Run demonstrations
    await demonstrate_global_api()
    await demonstrate_instance_api()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print("✅ Global API: Perfect for single-service applications")
    print("✅ Instance API: Perfect for microservices and multi-tenant apps")
    print("✅ Both APIs can be used together in the same application")
    print("✅ Jobs are completely isolated between different FastJob instances")
    
    print("\n🚀 Ready to choose your approach!")
    print("\nFor production deployment:")
    print("  Global API: fastjob worker --concurrency 4")
    print("  Instance API: See CLI documentation for --database-url usage")


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())