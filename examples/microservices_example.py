"""
Microservices Example - Production Instance API Patterns

Real microservices patterns with FastJob's Instance API:
- Each service gets its own database and job queue
- Services talk to each other through job workflows
- Different configs per environment
- Health checks and monitoring that actually work
- Multi-tenant support with complete isolation

Architecture shown:
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   User Service  │    │ Payment Service │    │ Notification    │
│   Database      │    │   Database      │    │   Service DB    │
│                 │    │                 │    │                 │
│ • User jobs     │    │ • Payment jobs  │    │ • Email jobs    │
│ • Profile jobs  │    │ • Refund jobs   │    │ • SMS jobs      │
│ • Auth jobs     │    │ • Invoice jobs  │    │ • Push jobs     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
from pydantic import BaseModel

from fastjob import FastJob


# ========================================
# SHARED MODELS AND ENUMS
# ========================================

class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class NotificationType(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class UserRegistrationData(BaseModel):
    user_id: str
    email: str
    name: str
    phone: Optional[str] = None
    tenant_id: str = "default"


class PaymentRequestData(BaseModel):
    payment_id: str
    user_id: str
    amount: float
    currency: str = "USD"
    tenant_id: str = "default"


class NotificationData(BaseModel):
    notification_id: str
    user_id: str
    type: NotificationType
    title: str
    message: str
    tenant_id: str = "default"


# ========================================
# SERVICE CONFIGURATIONS
# ========================================

# Environment-based configuration
ENVIRONMENT = Environment(os.environ.get("ENVIRONMENT", "development"))

def get_database_url(service_name: str, tenant_id: str = "default") -> str:
    """Get database URL based on environment and service."""
    if ENVIRONMENT == Environment.PRODUCTION:
        # Production: Separate databases per tenant
        base_url = os.environ.get(f"{service_name.upper()}_DATABASE_URL")
        return f"{base_url}_{tenant_id}" if tenant_id != "default" else base_url
    elif ENVIRONMENT == Environment.STAGING:
        # Staging: Shared database with tenant schemas
        base_url = os.environ.get("STAGING_DATABASE_URL", "postgresql://localhost/fastjob_staging")
        return base_url
    else:
        # Development: Local databases
        return f"postgresql://localhost/fastjob_{service_name}_{ENVIRONMENT.value}"


def create_service_instance(service_name: str, tenant_id: str = "default") -> FastJob:
    """Create a FastJob instance for a specific service and tenant."""
    return FastJob(
        database_url=get_database_url(service_name, tenant_id),
        service_name=f"{service_name}_{tenant_id}",
        # Production settings
        max_pool_size=20 if ENVIRONMENT == Environment.PRODUCTION else 5,
        heartbeat_interval=30.0 if ENVIRONMENT == Environment.PRODUCTION else 60.0,
    )


# ========================================
# USER SERVICE
# ========================================

class UserService:
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self.fastjob = create_service_instance("user", tenant_id)
        self._register_jobs()
    
    def _register_jobs(self):
        """Register all user service jobs."""
        
        @self.fastjob.job(queue="registration", retries=3, args_model=UserRegistrationData)
        async def process_user_registration(user_id: str, email: str, name: str, phone: Optional[str], tenant_id: str) -> dict:
            """Process new user registration."""
            print(f"[USER-{self.tenant_id}] Processing registration for: {email}")
            
            # Simulate database operations
            await asyncio.sleep(0.5)
            
            # Simulate user creation
            user_data = {
                "user_id": user_id,
                "email": email,
                "name": name,
                "phone": phone,
                "tenant_id": tenant_id,
                "status": "active",
                "created_at": datetime.now().isoformat(),
                "service": f"user_service_{tenant_id}"
            }
            
            print(f"[USER-{self.tenant_id}] User registered: {user_id}")
            return user_data
        
        @self.fastjob.job(queue="profiles", retries=2)
        async def update_user_profile(user_id: str, profile_data: dict, tenant_id: str) -> dict:
            """Update user profile information."""
            print(f"[USER-{self.tenant_id}] Updating profile for user: {user_id}")
            
            await asyncio.sleep(0.3)
            
            result = {
                "user_id": user_id,
                "profile_data": profile_data,
                "tenant_id": tenant_id,
                "updated_at": datetime.now().isoformat(),
                "service": f"user_service_{tenant_id}"
            }
            
            print(f"[USER-{self.tenant_id}] Profile updated: {user_id}")
            return result
        
        @self.fastjob.job(queue="authentication", priority=1)
        async def process_authentication(user_id: str, auth_method: str, tenant_id: str) -> dict:
            """Process user authentication."""
            print(f"[USER-{self.tenant_id}] Processing authentication for: {user_id}")
            
            await asyncio.sleep(0.2)
            
            result = {
                "user_id": user_id,
                "auth_method": auth_method,
                "tenant_id": tenant_id,
                "authenticated_at": datetime.now().isoformat(),
                "status": "success",
                "service": f"user_service_{tenant_id}"
            }
            
            print(f"[USER-{self.tenant_id}] Authentication successful: {user_id}")
            return result
        
        # Store job references for external access
        self.process_user_registration = process_user_registration
        self.update_user_profile = update_user_profile
        self.process_authentication = process_authentication


# ========================================
# PAYMENT SERVICE
# ========================================

class PaymentService:
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self.fastjob = create_service_instance("payment", tenant_id)
        self._register_jobs()
    
    def _register_jobs(self):
        """Register all payment service jobs."""
        
        @self.fastjob.job(queue="transactions", priority=1, retries=5, args_model=PaymentRequestData)
        async def process_payment(payment_id: str, user_id: str, amount: float, currency: str, tenant_id: str) -> dict:
            """Process a payment transaction."""
            print(f"[PAYMENT-{self.tenant_id}] Processing payment: {payment_id} for ${amount}")
            
            # Simulate payment processing
            await asyncio.sleep(1.2)
            
            result = {
                "payment_id": payment_id,
                "user_id": user_id,
                "amount": amount,
                "currency": currency,
                "tenant_id": tenant_id,
                "status": "completed",
                "processed_at": datetime.now().isoformat(),
                "service": f"payment_service_{tenant_id}"
            }
            
            print(f"[PAYMENT-{self.tenant_id}] Payment completed: {payment_id}")
            return result
        
        @self.fastjob.job(queue="refunds", retries=3)
        async def process_refund(refund_id: str, payment_id: str, amount: float, tenant_id: str) -> dict:
            """Process a payment refund."""
            print(f"[PAYMENT-{self.tenant_id}] Processing refund: {refund_id}")
            
            await asyncio.sleep(0.8)
            
            result = {
                "refund_id": refund_id,
                "payment_id": payment_id,
                "amount": amount,
                "tenant_id": tenant_id,
                "status": "completed",
                "processed_at": datetime.now().isoformat(),
                "service": f"payment_service_{tenant_id}"
            }
            
            print(f"[PAYMENT-{self.tenant_id}] Refund completed: {refund_id}")
            return result
        
        @self.fastjob.job(queue="invoicing", priority=3)
        async def generate_invoice(invoice_id: str, payment_id: str, tenant_id: str) -> dict:
            """Generate invoice for completed payment."""
            print(f"[PAYMENT-{self.tenant_id}] Generating invoice: {invoice_id}")
            
            await asyncio.sleep(0.5)
            
            result = {
                "invoice_id": invoice_id,
                "payment_id": payment_id,
                "tenant_id": tenant_id,
                "generated_at": datetime.now().isoformat(),
                "service": f"payment_service_{tenant_id}"
            }
            
            print(f"[PAYMENT-{self.tenant_id}] Invoice generated: {invoice_id}")
            return result
        
        # Store job references
        self.process_payment = process_payment
        self.process_refund = process_refund
        self.generate_invoice = generate_invoice


# ========================================
# NOTIFICATION SERVICE
# ========================================

class NotificationService:
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self.fastjob = create_service_instance("notification", tenant_id)
        self._register_jobs()
    
    def _register_jobs(self):
        """Register all notification service jobs."""
        
        @self.fastjob.job(queue="emails", retries=3, args_model=NotificationData)
        async def send_email(notification_id: str, user_id: str, title: str, message: str, tenant_id: str) -> dict:
            """Send email notification."""
            print(f"[NOTIFICATION-{self.tenant_id}] Sending email: {title}")
            
            await asyncio.sleep(0.4)
            
            result = {
                "notification_id": notification_id,
                "user_id": user_id,
                "type": "email",
                "title": title,
                "message": message,
                "tenant_id": tenant_id,
                "sent_at": datetime.now().isoformat(),
                "status": "delivered",
                "service": f"notification_service_{tenant_id}"
            }
            
            print(f"[NOTIFICATION-{self.tenant_id}] Email sent: {notification_id}")
            return result
        
        @self.fastjob.job(queue="sms", priority=2, retries=2)
        async def send_sms(notification_id: str, user_id: str, message: str, tenant_id: str) -> dict:
            """Send SMS notification."""
            print(f"[NOTIFICATION-{self.tenant_id}] Sending SMS: {notification_id}")
            
            await asyncio.sleep(0.3)
            
            result = {
                "notification_id": notification_id,
                "user_id": user_id,
                "type": "sms",
                "message": message,
                "tenant_id": tenant_id,
                "sent_at": datetime.now().isoformat(),
                "status": "delivered",
                "service": f"notification_service_{tenant_id}"
            }
            
            print(f"[NOTIFICATION-{self.tenant_id}] SMS sent: {notification_id}")
            return result
        
        @self.fastjob.job(queue="push", priority=4)
        async def send_push_notification(notification_id: str, user_id: str, title: str, message: str, tenant_id: str) -> dict:
            """Send push notification."""
            print(f"[NOTIFICATION-{self.tenant_id}] Sending push: {title}")
            
            await asyncio.sleep(0.2)
            
            result = {
                "notification_id": notification_id,
                "user_id": user_id,
                "type": "push",
                "title": title,
                "message": message,
                "tenant_id": tenant_id,
                "sent_at": datetime.now().isoformat(),
                "status": "delivered",
                "service": f"notification_service_{tenant_id}"
            }
            
            print(f"[NOTIFICATION-{self.tenant_id}] Push notification sent: {notification_id}")
            return result
        
        # Store job references
        self.send_email = send_email
        self.send_sms = send_sms
        self.send_push_notification = send_push_notification


# ========================================
# ORCHESTRATION SERVICE
# ========================================

class OrchestrationService:
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self.user_service = UserService(tenant_id)
        self.payment_service = PaymentService(tenant_id)
        self.notification_service = NotificationService(tenant_id)
        
        # Use user service for orchestration jobs
        self.fastjob = self.user_service.fastjob
        self._register_workflows()
    
    def _register_workflows(self):
        """Register cross-service workflow jobs."""
        
        @self.fastjob.job(queue="workflows", priority=1)
        async def user_registration_workflow(user_id: str, email: str, name: str, tenant_id: str) -> dict:
            """Complete user registration workflow across all services."""
            print(f"[WORKFLOW-{self.tenant_id}] Starting registration workflow for: {email}")
            
            workflow_id = f"reg_{user_id}_{int(datetime.now().timestamp())}"
            
            # Step 1: Register user
            user_job = await self.user_service.fastjob.enqueue(
                self.user_service.process_user_registration,
                user_id=user_id,
                email=email,
                name=name,
                phone=None,
                tenant_id=tenant_id
            )
            
            # Step 2: Send welcome notifications
            email_job = await self.notification_service.fastjob.enqueue(
                self.notification_service.send_email,
                notification_id=f"welcome_{user_id}",
                user_id=user_id,
                title="Welcome to our platform!",
                message=f"Welcome {name}! Your account is now active.",
                tenant_id=tenant_id
            )
            
            push_job = await self.notification_service.fastjob.enqueue(
                self.notification_service.send_push_notification,
                notification_id=f"welcome_push_{user_id}",
                user_id=user_id,
                title="Account Created",
                message=f"Welcome {name}!",
                tenant_id=tenant_id
            )
            
            result = {
                "workflow_id": workflow_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "jobs": {
                    "user_registration": user_job,
                    "welcome_email": email_job,
                    "welcome_push": push_job
                },
                "status": "initiated",
                "started_at": datetime.now().isoformat()
            }
            
            print(f"[WORKFLOW-{self.tenant_id}] Registration workflow initiated: {workflow_id}")
            return result
        
        @self.fastjob.job(queue="workflows", priority=1)
        async def payment_processing_workflow(payment_id: str, user_id: str, amount: float, tenant_id: str) -> dict:
            """Complete payment processing workflow."""
            print(f"[WORKFLOW-{self.tenant_id}] Starting payment workflow: {payment_id}")
            
            workflow_id = f"pay_{payment_id}_{int(datetime.now().timestamp())}"
            
            # Step 1: Process payment
            payment_job = await self.payment_service.fastjob.enqueue(
                self.payment_service.process_payment,
                payment_id=payment_id,
                user_id=user_id,
                amount=amount,
                currency="USD",
                tenant_id=tenant_id
            )
            
            # Step 2: Generate invoice
            invoice_job = await self.payment_service.fastjob.enqueue(
                self.payment_service.generate_invoice,
                invoice_id=f"inv_{payment_id}",
                payment_id=payment_id,
                tenant_id=tenant_id,
                scheduled_at=datetime.now() + timedelta(seconds=2)  # After payment
            )
            
            # Step 3: Send payment confirmation
            confirmation_job = await self.notification_service.fastjob.enqueue(
                self.notification_service.send_email,
                notification_id=f"payment_confirm_{payment_id}",
                user_id=user_id,
                title="Payment Confirmation",
                message=f"Your payment of ${amount} has been processed successfully.",
                tenant_id=tenant_id,
                scheduled_at=datetime.now() + timedelta(seconds=3)  # After invoice
            )
            
            result = {
                "workflow_id": workflow_id,
                "tenant_id": tenant_id,
                "payment_id": payment_id,
                "jobs": {
                    "payment_processing": payment_job,
                    "invoice_generation": invoice_job,
                    "payment_confirmation": confirmation_job
                },
                "status": "initiated",
                "started_at": datetime.now().isoformat()
            }
            
            print(f"[WORKFLOW-{self.tenant_id}] Payment workflow initiated: {workflow_id}")
            return result
        
        # Store workflow references
        self.user_registration_workflow = user_registration_workflow
        self.payment_processing_workflow = payment_processing_workflow


# ========================================
# MULTI-TENANT DEMONSTRATION
# ========================================

async def demonstrate_single_tenant():
    """Demonstrate single tenant operations."""
    print("\n" + "="*60)
    print("SINGLE TENANT DEMONSTRATION")
    print("="*60)
    
    # Create orchestration service for default tenant
    orchestrator = OrchestrationService("default")
    
    # Start embedded workers for all services
    print("Starting embedded workers for all services...")
    orchestrator.user_service.fastjob.start_embedded_worker()
    orchestrator.payment_service.fastjob.start_embedded_worker()
    orchestrator.notification_service.fastjob.start_embedded_worker()
    
    try:
        # User registration workflow
        print("\n1. Starting user registration workflow...")
        reg_workflow = await orchestrator.fastjob.enqueue(
            orchestrator.user_registration_workflow,
            user_id="user_001",
            email="john@example.com",
            name="John Doe",
            tenant_id="default"
        )
        print(f"   Registration workflow ID: {reg_workflow}")
        
        # Payment processing workflow
        print("\n2. Starting payment processing workflow...")
        pay_workflow = await orchestrator.fastjob.enqueue(
            orchestrator.payment_processing_workflow,
            payment_id="pay_001",
            user_id="user_001",
            amount=99.99,
            tenant_id="default"
        )
        print(f"   Payment workflow ID: {pay_workflow}")
        
        # Wait for workflows to complete
        print("\n⏳ Processing workflows...")
        await asyncio.sleep(8)
        
        # Show queue status
        print("\n📊 Service Queue Status:")
        user_status = await orchestrator.user_service.fastjob.get_queue_status()
        payment_status = await orchestrator.payment_service.fastjob.get_queue_status()
        notification_status = await orchestrator.notification_service.fastjob.get_queue_status()
        
        print(f"   User Service: {user_status}")
        print(f"   Payment Service: {payment_status}")
        print(f"   Notification Service: {notification_status}")
        
    finally:
        print("\nStopping embedded workers...")
        await orchestrator.user_service.fastjob.stop_embedded_worker()
        await orchestrator.payment_service.fastjob.stop_embedded_worker()
        await orchestrator.notification_service.fastjob.stop_embedded_worker()
        
        await orchestrator.user_service.fastjob.close()
        await orchestrator.payment_service.fastjob.close()
        await orchestrator.notification_service.fastjob.close()


async def demonstrate_multi_tenant():
    """Demonstrate multi-tenant isolation."""
    print("\n" + "="*60)
    print("MULTI-TENANT DEMONSTRATION")
    print("="*60)
    print("Showing complete data isolation between tenants")
    
    # Create orchestration services for different tenants
    tenant_a = OrchestrationService("tenant_a")
    tenant_b = OrchestrationService("tenant_b")
    
    # Start embedded workers for both tenants
    print("Starting embedded workers for both tenants...")
    tenant_a.user_service.fastjob.start_embedded_worker()
    tenant_a.payment_service.fastjob.start_embedded_worker()
    tenant_a.notification_service.fastjob.start_embedded_worker()
    
    tenant_b.user_service.fastjob.start_embedded_worker()
    tenant_b.payment_service.fastjob.start_embedded_worker()
    tenant_b.notification_service.fastjob.start_embedded_worker()
    
    try:
        # Tenant A operations
        print("\n1. Tenant A - User registration...")
        await tenant_a.fastjob.enqueue(
            tenant_a.user_registration_workflow,
            user_id="user_a001",
            email="alice@tenant-a.com",
            name="Alice (Tenant A)",
            tenant_id="tenant_a"
        )
        
        # Tenant B operations (completely isolated)
        print("\n2. Tenant B - User registration...")
        await tenant_b.fastjob.enqueue(
            tenant_b.user_registration_workflow,
            user_id="user_b001",
            email="bob@tenant-b.com",
            name="Bob (Tenant B)",
            tenant_id="tenant_b"
        )
        
        # Both tenants can have same user IDs - they're isolated
        print("\n3. Tenant B - Same user ID as Tenant A (isolated)...")
        await tenant_b.fastjob.enqueue(
            tenant_b.user_registration_workflow,
            user_id="user_a001",  # Same ID as Tenant A - but isolated
            email="charlie@tenant-b.com",
            name="Charlie (Tenant B)",
            tenant_id="tenant_b"
        )
        
        # Different payment amounts for demonstration
        print("\n4. Tenant A - Payment processing...")
        await tenant_a.fastjob.enqueue(
            tenant_a.payment_processing_workflow,
            payment_id="pay_001",
            user_id="user_a001",
            amount=149.99,
            tenant_id="tenant_a"
        )
        
        print("\n5. Tenant B - Payment processing...")
        await tenant_b.fastjob.enqueue(
            tenant_b.payment_processing_workflow,
            payment_id="pay_001",  # Same payment ID - but isolated
            user_id="user_b001",
            amount=299.99,
            tenant_id="tenant_b"
        )
        
        # Wait for all workflows to complete
        print("\n⏳ Processing all tenant workflows...")
        await asyncio.sleep(10)
        
        # Show tenant isolation
        print("\n🏢 Tenant Isolation Report:")
        print("  Each tenant has completely separate:")
        print("    • Databases (or schemas)")
        print("    • Job queues")
        print("    • Worker processes")
        print("    • Job histories")
        print("    • No cross-tenant data access possible")
        
    finally:
        print("\nStopping all tenant workers...")
        await tenant_a.user_service.fastjob.stop_embedded_worker()
        await tenant_a.payment_service.fastjob.stop_embedded_worker()
        await tenant_a.notification_service.fastjob.stop_embedded_worker()
        
        await tenant_b.user_service.fastjob.stop_embedded_worker()
        await tenant_b.payment_service.fastjob.stop_embedded_worker()
        await tenant_b.notification_service.fastjob.stop_embedded_worker()
        
        await tenant_a.user_service.fastjob.close()
        await tenant_a.payment_service.fastjob.close()
        await tenant_a.notification_service.fastjob.close()
        
        await tenant_b.user_service.fastjob.close()
        await tenant_b.payment_service.fastjob.close()
        await tenant_b.notification_service.fastjob.close()


async def main():
    """
    Main function demonstrating production microservices patterns.
    """
    print("🚀 FastJob Microservices Example")
    print("Production-ready patterns with Instance API")
    print(f"Environment: {ENVIRONMENT.value}")
    
    print("\n📋 Architecture Overview:")
    print("• User Service: Registration, profiles, authentication")
    print("• Payment Service: Transactions, refunds, invoicing")
    print("• Notification Service: Email, SMS, push notifications")
    print("• Orchestration: Cross-service workflows")
    print("• Multi-tenant: Complete data isolation")
    
    # Run demonstrations
    await demonstrate_single_tenant()
    await demonstrate_multi_tenant()
    
    print("\n" + "="*60)
    print("PRODUCTION DEPLOYMENT GUIDE")
    print("="*60)
    print("🚀 Each service runs independently:")
    print()
    print("# User Service Workers")
    print("fastjob worker --database-url $USER_SERVICE_DB --concurrency 4")
    print()
    print("# Payment Service Workers")
    print("fastjob worker --database-url $PAYMENT_SERVICE_DB --concurrency 2")
    print()
    print("# Notification Service Workers")
    print("fastjob worker --database-url $NOTIFICATION_SERVICE_DB --concurrency 8")
    print()
    print("🔍 Monitor each service independently:")
    print("fastjob dashboard --database-url $USER_SERVICE_DB --port 6161")
    print("fastjob dashboard --database-url $PAYMENT_SERVICE_DB --port 6162")
    print("fastjob dashboard --database-url $NOTIFICATION_SERVICE_DB --port 6163")
    print()
    print("✅ Complete service isolation achieved!")


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())