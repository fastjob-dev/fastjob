"""
Email-related background jobs
"""

import asyncio

import fastjob


@fastjob.job()
async def send_welcome_email(user_email: str, name: str):
    """Send a welcome email to new users."""
    print(f"📧 Sending welcome email to {name} at {user_email}")
    await asyncio.sleep(0.5)  # Simulate email delivery
    print(f"✅ Welcome email sent to {name}")


@fastjob.job(priority=1, queue="urgent")
async def send_password_reset_email(user_email: str, reset_token: str):
    """Send password reset email - high priority."""
    print(f"🔐 Sending password reset to {user_email}")
    await asyncio.sleep(0.3)  # Simulate email delivery
    print(f"✅ Password reset email sent to {user_email}")


@fastjob.job(retries=3)
async def send_newsletter(subscriber_emails: list[str], subject: str):
    """Send newsletter to multiple subscribers."""
    print(f"📰 Sending newsletter '{subject}' to {len(subscriber_emails)} subscribers")

    for email in subscriber_emails:
        print(f"  → Sending to {email}")
        await asyncio.sleep(0.1)  # Simulate individual email sending

    print(f"✅ Newsletter sent to all {len(subscriber_emails)} subscribers")
