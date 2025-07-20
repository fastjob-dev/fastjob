"""
FastJob Idempotency Guide
Demonstrates how to design idempotent job functions for reliable processing.

Idempotent jobs can be executed multiple times with the same result,
preventing unintended side effects from retries or duplicate enqueues.
"""

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel

import fastjob


# Example 1: Using unique identifiers to prevent duplicate processing
class EmailJobArgs(BaseModel):
    recipient_id: int
    email_type: str
    template_data: Dict[str, Any]
    idempotency_key: str

# In-memory store for demo (use Redis/database in production)
_processed_emails = set()

@fastjob.job(retries=3)
async def send_idempotent_email(
    recipient_id: int,
    email_type: str,
    template_data: Dict[str, Any],
    idempotency_key: str
) -> dict:
    """
    Idempotent email sending job.
    
    Uses an idempotency key to ensure the same email is not sent multiple times,
    even if the job is retried or accidentally enqueued multiple times.
    """
    print(f"📧 Processing email job with key: {idempotency_key}")
    
    # Check if we've already processed this email
    if idempotency_key in _processed_emails:
        print(f"   ⚠️ Email already sent (idempotency key: {idempotency_key})")
        return {
            "status": "already_sent",
            "recipient_id": recipient_id,
            "email_type": email_type,
            "idempotency_key": idempotency_key,
            "note": "Skipped due to idempotency"
        }
    
    # Simulate email sending
    print(f"   📤 Sending {email_type} email to recipient {recipient_id}")
    await asyncio.sleep(0.5)  # Simulate email service call
    
    # Mark as processed (this should be atomic in production)
    _processed_emails.add(idempotency_key)
    
    result = {
        "status": "sent",
        "recipient_id": recipient_id,
        "email_type": email_type,
        "sent_at": datetime.now().isoformat(),
        "idempotency_key": idempotency_key
    }
    
    print(f"   ✅ Email sent successfully")
    return result


# Example 2: Database operations with upsert patterns
class UserProfileUpdate(BaseModel):
    user_id: int
    profile_data: Dict[str, Any]
    version: Optional[int] = None

# Simulated database
_user_profiles = {}

@fastjob.job(retries=3)
async def update_user_profile_idempotent(
    user_id: int,
    profile_data: Dict[str, Any],
    version: Optional[int] = None
) -> dict:
    """
    Idempotent user profile update using versioning.
    
    Uses optimistic locking with version numbers to ensure
    updates are applied correctly even with retries.
    """
    print(f"👤 Updating profile for user {user_id} (version: {version})")
    
    # Get current profile
    current_profile = _user_profiles.get(user_id, {"version": 0, "data": {}})
    
    # Check version for idempotency
    if version is not None and current_profile["version"] >= version:
        print(f"   ⚠️ Profile version {version} already applied or superseded")
        return {
            "status": "already_applied",
            "user_id": user_id,
            "current_version": current_profile["version"],
            "requested_version": version
        }
    
    # Apply update (simulate database operation)
    new_version = (current_profile["version"] + 1) if version is None else version
    
    # Merge profile data
    updated_data = {**current_profile["data"], **profile_data}
    
    # Update profile atomically
    _user_profiles[user_id] = {
        "version": new_version,
        "data": updated_data,
        "updated_at": datetime.now().isoformat()
    }
    
    result = {
        "status": "updated",
        "user_id": user_id,
        "version": new_version,
        "updated_fields": list(profile_data.keys())
    }
    
    print(f"   ✅ Profile updated to version {new_version}")
    return result


# Example 3: File processing with checksums
@fastjob.job(retries=3)
async def process_file_idempotent(file_path: str, output_path: str) -> dict:
    """
    Idempotent file processing using content checksums.
    
    Checks if the output already exists and matches expected content
    to avoid reprocessing the same file.
    """
    print(f"📁 Processing file: {file_path}")
    
    # Calculate input file checksum (simulate reading file)
    file_content = f"content_of_{file_path}_{datetime.now().strftime('%H%M')}"
    input_checksum = hashlib.md5(file_content.encode()).hexdigest()
    
    print(f"   🔍 Input checksum: {input_checksum}")
    
    # Check if output already exists with same checksum
    # In real implementation, check if output file exists and read its metadata
    output_exists = False  # Simulate checking output file
    
    if output_exists:
        print(f"   ⚠️ Output file already exists with matching checksum")
        return {
            "status": "already_processed",
            "input_path": file_path,
            "output_path": output_path,
            "checksum": input_checksum,
            "note": "Skipped processing - output already exists"
        }
    
    # Process file (simulate processing)
    print(f"   ⚙️ Processing file content...")
    await asyncio.sleep(1)  # Simulate processing time
    
    processed_content = f"processed_{file_content}"
    output_checksum = hashlib.md5(processed_content.encode()).hexdigest()
    
    # Write output file (simulate)
    print(f"   💾 Writing output to: {output_path}")
    
    result = {
        "status": "processed",
        "input_path": file_path,
        "output_path": output_path,
        "input_checksum": input_checksum,
        "output_checksum": output_checksum,
        "processed_at": datetime.now().isoformat()
    }
    
    print(f"   ✅ File processed successfully")
    return result


# Example 4: API calls with idempotency tokens
_api_calls = {}  # Simulate API call tracking

@fastjob.job(retries=3)
async def make_idempotent_api_call(
    endpoint: str,
    payload: Dict[str, Any],
    idempotency_token: str
) -> dict:
    """
    Idempotent API call using idempotency tokens.
    
    Many APIs support idempotency tokens to ensure that the same
    request is not processed multiple times.
    """
    print(f"🌐 Making API call to {endpoint} with token: {idempotency_token}")
    
    # Check if we've already made this API call
    if idempotency_token in _api_calls:
        cached_response = _api_calls[idempotency_token]
        print(f"   ♻️ Returning cached API response")
        return {
            "status": "cached",
            "response": cached_response,
            "idempotency_token": idempotency_token,
            "note": "Response retrieved from cache"
        }
    
    # Make API call (simulate)
    print(f"   📡 Calling API endpoint: {endpoint}")
    await asyncio.sleep(0.8)  # Simulate API call
    
    # Simulate API response
    api_response = {
        "id": f"api_response_{idempotency_token[-8:]}",
        "status": "success",
        "data": payload,
        "timestamp": datetime.now().isoformat()
    }
    
    # Cache the response
    _api_calls[idempotency_token] = api_response
    
    result = {
        "status": "success",
        "endpoint": endpoint,
        "response": api_response,
        "idempotency_token": idempotency_token
    }
    
    print(f"   ✅ API call completed successfully")
    return result


# Example 5: Aggregation jobs with checkpoint mechanism
_aggregation_checkpoints = {}

@fastjob.job(retries=3)
async def aggregate_data_idempotent(
    data_source: str,
    time_range: str,
    checkpoint_key: str
) -> dict:
    """
    Idempotent data aggregation using checkpoints.
    
    Uses checkpoints to track progress and avoid reprocessing
    data that has already been aggregated.
    """
    print(f"📊 Aggregating data from {data_source} for {time_range}")
    
    # Check if we have a checkpoint for this aggregation
    checkpoint = _aggregation_checkpoints.get(checkpoint_key, {
        "processed_batches": 0,
        "total_records": 0,
        "last_batch_id": None
    })
    
    if checkpoint["processed_batches"] > 0:
        print(f"   📋 Resuming from checkpoint: {checkpoint['processed_batches']} batches processed")
    
    # Simulate data processing in batches
    total_batches = 5
    
    for batch_num in range(checkpoint["processed_batches"], total_batches):
        batch_id = f"batch_{batch_num}_{time_range}"
        
        print(f"   ⚙️ Processing batch {batch_num + 1}/{total_batches}: {batch_id}")
        await asyncio.sleep(0.3)  # Simulate batch processing
        
        # Update checkpoint after each batch
        checkpoint["processed_batches"] = batch_num + 1
        checkpoint["total_records"] += 100  # Simulate records processed
        checkpoint["last_batch_id"] = batch_id
        
        # Save checkpoint (should be atomic in production)
        _aggregation_checkpoints[checkpoint_key] = checkpoint.copy()
    
    # Final result
    result = {
        "status": "completed",
        "data_source": data_source,
        "time_range": time_range,
        "total_batches": total_batches,
        "total_records": checkpoint["total_records"],
        "completed_at": datetime.now().isoformat(),
        "checkpoint_key": checkpoint_key
    }
    
    # Clean up checkpoint on successful completion
    if checkpoint_key in _aggregation_checkpoints:
        del _aggregation_checkpoints[checkpoint_key]
    
    print(f"   ✅ Data aggregation completed: {checkpoint['total_records']} records")
    return result


def generate_idempotency_key(*args, **kwargs) -> str:
    """
    Generate a consistent idempotency key from job arguments.
    
    This ensures the same arguments always produce the same key.
    """
    # Create a deterministic string from arguments
    key_data = {
        "args": args,
        "kwargs": sorted(kwargs.items())  # Sort for consistency
    }
    
    key_string = json.dumps(key_data, sort_keys=True, default=str)
    
    # Generate hash
    return hashlib.sha256(key_string.encode()).hexdigest()[:16]


async def demo_idempotency_patterns():
    """Demonstrate various idempotency patterns."""
    print("\n🔄 Idempotency Patterns Demo")
    print("=" * 40)
    
    # Example 1: Email with idempotency key
    print("\n1. Idempotent email sending...")
    email_key = generate_idempotency_key("welcome_email", 12345)
    
    # Send email twice - second call should be idempotent
    for attempt in [1, 2]:
        print(f"   Attempt {attempt}:")
        job_id = await fastjob.enqueue(
            send_idempotent_email,
            recipient_id=12345,
            email_type="welcome_email",
            template_data={"name": "John Doe"},
            idempotency_key=email_key
        )
        print(f"   Job ID: {job_id}")
    
    # Example 2: Profile update with versioning
    print("\n2. Idempotent profile updates...")
    
    # First update
    await fastjob.enqueue(
        update_user_profile_idempotent,
        user_id=12345,
        profile_data={"name": "John Doe", "email": "john@example.com"},
        version=1
    )
    
    # Second update with same version (should be idempotent)
    await fastjob.enqueue(
        update_user_profile_idempotent,
        user_id=12345,
        profile_data={"name": "John Doe", "email": "john@example.com"},
        version=1
    )
    
    # Third update with new version
    await fastjob.enqueue(
        update_user_profile_idempotent,
        user_id=12345,
        profile_data={"phone": "+1-555-0123"},
        version=2
    )
    
    # Example 3: File processing
    print("\n3. Idempotent file processing...")
    await fastjob.enqueue(
        process_file_idempotent,
        file_path="/data/input/report.csv",
        output_path="/data/output/processed_report.json"
    )
    
    # Example 4: API call with idempotency token
    print("\n4. Idempotent API calls...")
    api_token = generate_idempotency_key("create_order", {"customer_id": 789})
    
    await fastjob.enqueue(
        make_idempotent_api_call,
        endpoint="https://api.example.com/orders",
        payload={"customer_id": 789, "amount": 99.99},
        idempotency_token=api_token
    )
    
    # Example 5: Data aggregation with checkpoints
    print("\n5. Idempotent data aggregation...")
    checkpoint_key = generate_idempotency_key("daily_aggregation", "2025-01-19")
    
    await fastjob.enqueue(
        aggregate_data_idempotent,
        data_source="user_events",
        time_range="2025-01-19",
        checkpoint_key=checkpoint_key
    )


async def main():
    """Main example demonstrating idempotency best practices."""
    print("🔄 FastJob Idempotency Guide")
    print("=" * 50)
    
    print("\n📋 Idempotency Best Practices:")
    print("1. Use unique identifiers (idempotency keys)")
    print("2. Implement versioning for data updates")
    print("3. Use checksums for file operations")
    print("4. Leverage API idempotency tokens")
    print("5. Implement checkpoint mechanisms for long operations")
    print("6. Make state changes atomic")
    print("7. Store idempotency tracking data persistently")
    
    # Start embedded worker
    print("\nStarting embedded worker...")
    fastjob.start_embedded_worker()
    
    try:
        await demo_idempotency_patterns()
        
        # Wait for jobs to process
        print("\n⏳ Processing idempotent jobs...")
        await asyncio.sleep(8)
        
        print("\n✅ Idempotency demo completed!")
        print("\n💡 Key Takeaways:")
        print("• Always design jobs to be idempotent")
        print("• Use unique keys to prevent duplicate processing")
        print("• Implement proper error handling and state tracking")
        print("• Test idempotency by running jobs multiple times")
        print("• Consider using database transactions for atomic operations")
        
    finally:
        # Stop embedded worker
        print("\nStopping embedded worker...")
        await fastjob.stop_embedded_worker()


if __name__ == "__main__":
    asyncio.run(main())