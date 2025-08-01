# FastJob Examples

Examples showing different FastJob patterns. Pick the one that matches what you're building.

## 🚀 Getting Started Examples

### [`basic_example.py`](basic_example.py)
**Perfect for:** Learning FastJob fundamentals

- Simple job definition and enqueueing
- Retry mechanisms and error handling
- Scheduled jobs and timing
- Embedded worker for development
- **Uses:** Global API (single database)

```bash
python3 examples/basic_example.py
```

### [`comprehensive_example.py`](comprehensive_example.py)
**Perfect for:** Understanding all FastJob features

- Both Global API and Instance API patterns
- Priority queues and validation
- Scheduling and timing features
- Cross-service workflows (Instance API)
- Queue statistics and monitoring
- **Uses:** Both Global and Instance APIs

```bash
python3 examples/comprehensive_example.py
```

---

## 🏗️ Architecture Pattern Examples

### [`instance_api_example.py`](instance_api_example.py)
**Perfect for:** Choosing between Global and Instance APIs

- Side-by-side comparison of both approaches
- When to use Global vs Instance API
- Service isolation patterns
- Cross-service communication
- **Uses:** Both APIs with clear comparisons

```bash
python3 examples/instance_api_example.py
```

### [`microservices_example.py`](microservices_example.py)
**Perfect for:** Production microservices architecture

- Multi-service job processing
- Complete data isolation between services
- Cross-service workflows and orchestration
- Multi-tenant patterns with tenant isolation
- Environment-specific configurations
- **Uses:** Instance API (multiple databases)

```bash
python3 examples/microservices_example.py
```

---

## 🛠️ Specialized Examples

### [`fastapi_integration.py`](fastapi_integration.py)
**Perfect for:** FastAPI web applications

- FastAPI background job patterns
- API endpoint job triggering
- Request-response job workflows
- **Uses:** Global API

### [`enhanced_features_example.py`](enhanced_features_example.py)
**Perfect for:** Advanced FastJob features

- Complex job patterns
- Advanced error handling
- Production monitoring
- **Uses:** Global API

### [`idempotency_guide.py`](idempotency_guide.py)
**Perfect for:** Ensuring job idempotency

- Idempotent job design patterns
- Duplicate job handling
- Safe retry mechanisms
- **Uses:** Global API

---

## 📁 Directory Structure Examples

### [`jobs_directory_example/`](jobs_directory_example/)
**Perfect for:** Organizing jobs in larger applications

- Job organization patterns
- Module structure for scalable apps
- Job discovery and registration
- **Uses:** Global API

### [`automatic_plugin_loading_demo.py`](automatic_plugin_loading_demo.py)
**Perfect for:** Plugin-based architectures

- Dynamic job loading
- Plugin system patterns
- Modular job organization
- **Uses:** Global API

---

## 🚀 Production Examples

### [`production/`](production/)
**Perfect for:** Production deployment patterns

- Worker monitoring and management
- Health checks and alerting
- Scaling and performance optimization
- **Uses:** Both APIs

---

## 🤔 Which Example Should I Use?

### Starting with FastJob?
→ **Start with [`basic_example.py`](basic_example.py)**
- Learn core concepts
- Understand job definition and enqueueing
- See embedded worker in action

### Single application with background jobs?
→ **Use Global API examples**
- [`basic_example.py`](basic_example.py) - Learning
- [`comprehensive_example.py`](comprehensive_example.py) - All features
- [`fastapi_integration.py`](fastapi_integration.py) - Web apps

### Microservices or multi-tenant architecture?
→ **Use Instance API examples**
- [`instance_api_example.py`](instance_api_example.py) - Comparison
- [`microservices_example.py`](microservices_example.py) - Production patterns
- [`comprehensive_example.py`](comprehensive_example.py) - Both APIs

### Large application with many job types?
→ **Use organizational examples**
- [`jobs_directory_example/`](jobs_directory_example/) - Job organization
- [`automatic_plugin_loading_demo.py`](automatic_plugin_loading_demo.py) - Plugin patterns

---

## 🔧 API Pattern Quick Reference

### Global API Pattern
```python
import fastjob

@fastjob.job()
async def my_job(data: str):
    return f"Processed: {data}"

# Enqueue with global function
job_id = await fastjob.enqueue(my_job, data="hello")
```

**Best for:**
- Single application
- One job queue
- Simple setup
- Getting started

### Instance API Pattern
```python
from fastjob import FastJob

# Create service-specific instances
user_service = FastJob(database_url="postgresql://localhost/user_service")
payment_service = FastJob(database_url="postgresql://localhost/payment_service")

@user_service.job()
async def process_user(user_id: str):
    return f"User {user_id} processed"

@payment_service.job()
async def process_payment(payment_id: str):
    return f"Payment {payment_id} processed"

# Enqueue with instance methods
user_job = await user_service.enqueue(process_user, user_id="123")
payment_job = await payment_service.enqueue(process_payment, payment_id="456")
```

**Best for:**
- Microservices architecture
- Multi-tenant applications
- Service isolation
- Independent scaling

---

## 🚀 Running Examples

### Prerequisites
```bash
# Install FastJob
pip install fastjob

# Set up database (if not using embedded)
export FASTJOB_DATABASE_URL="postgresql://user:password@localhost/fastjob"
fastjob migrate
```

### Instance API Examples (Microservices)
```bash
# Set up service databases
export USER_SERVICE_DATABASE_URL="postgresql://localhost/user_service"
export PAYMENT_SERVICE_DATABASE_URL="postgresql://localhost/payment_service"
export ANALYTICS_DATABASE_URL="postgresql://localhost/analytics_service"

# Run example
python3 examples/microservices_example.py
```

### Production Examples
```bash
# Global API production worker
fastjob worker --concurrency 4

# Instance API production workers (one per service)
fastjob worker --database-url $USER_SERVICE_DATABASE_URL --concurrency 2
fastjob worker --database-url $PAYMENT_SERVICE_DATABASE_URL --concurrency 1
fastjob worker --database-url $ANALYTICS_DATABASE_URL --concurrency 4
```

---

## 📚 Further Reading

- **[FastJob Documentation](../README.md)** - Complete FastJob guide
- **[Instance API Guide](../docs/instance-api.md)** - Detailed Instance API documentation
- **[Production Guide](../docs/production.md)** - Production deployment patterns
- **[FastJob Pro](https://github.com/fastjob/fastjob-pro)** - Dashboard and advanced features
- **[FastJob Enterprise](https://github.com/fastjob/fastjob-enterprise)** - Metrics, logging, compliance

---

## 🤝 Contributing Examples

Have a useful FastJob pattern? We'd love to include it! Please:

1. Follow existing example structure
2. Include clear documentation
3. Show both Global and Instance API when relevant
4. Add your example to this README
5. Submit a pull request

Examples should be practical, well-documented, and show real-world usage patterns.