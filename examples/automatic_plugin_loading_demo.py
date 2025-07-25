#!/usr/bin/env python3
"""
Automatic Plugin Loading Demo

This example demonstrates FastJob's automatic plugin loading feature
and how to control it in testing scenarios.
"""

import asyncio
import os

# Set database for demo (in production, set via environment)
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_demo"


def demo_automatic_loading():
    """Demonstrate automatic plugin loading"""
    print("🚀 FastJob Automatic Plugin Loading Demo")
    print("=" * 50)
    
    print("\n1️⃣ Normal usage - plugins load automatically:")
    print("-" * 45)
    
    import fastjob
    
    # Define a job - plugins will load automatically when this decorator runs
    @fastjob.job(retries=3)
    async def example_job(message: str):
        return f"Processed: {message}"
    
    print("   ✅ Job decorated successfully")
    print("   📦 Plugins loaded automatically (if Pro/Enterprise installed)")
    
    async def enqueue_example():
        # This will also trigger plugin loading if not already loaded
        try:
            job_id = await fastjob.enqueue(example_job, message="Hello World")
            print(f"   📝 Job enqueued: {job_id}")
        except Exception as e:
            print(f"   ⚠️  Database not available for demo: {e}")
    
    # Run the async example
    try:
        asyncio.run(enqueue_example())
    except Exception as e:
        print(f"   ⚠️  Skipping enqueue demo: {e}")
    
    print("\n2️⃣ Testing scenario - disable plugins:")
    print("-" * 40)
    
    # Import testing utilities
    from fastjob.testing import disable_plugins, no_plugins, is_plugin_loading_disabled
    
    # Check initial state
    print(f"   📊 Initial plugin loading state: {'enabled' if not is_plugin_loading_disabled() else 'disabled'}")
    
    # Disable plugins globally
    disable_plugins()
    print("   🚫 Plugins disabled globally")
    print(f"   📊 Plugin loading state: {'enabled' if not is_plugin_loading_disabled() else 'disabled'}")
    
    # Define another job - plugins won't load
    @fastjob.job(retries=2)
    async def test_job(data: str):
        return f"Test: {data}"
    
    print("   ✅ Job decorated without loading plugins")
    
    print("\n3️⃣ Context manager - temporary disable:")
    print("-" * 42)
    
    # Re-enable for demo
    from fastjob.testing import enable_plugins
    enable_plugins()
    print(f"   📊 Re-enabled plugin loading: {'enabled' if not is_plugin_loading_disabled() else 'disabled'}")
    
    # Use context manager
    with no_plugins():
        print(f"   🔒 Inside context: {'enabled' if not is_plugin_loading_disabled() else 'disabled'}")
        
        @fastjob.job()
        async def context_job():
            return "context test"
        
        print("   ✅ Job decorated inside no_plugins context")
    
    print(f"   🔓 Outside context: {'enabled' if not is_plugin_loading_disabled() else 'disabled'}")
    
    print("\n4️⃣ Manual plugin loading:")
    print("-" * 30)
    
    # Reset state
    from fastjob.testing import reset_plugin_state
    reset_plugin_state()
    
    # Load plugins manually
    fastjob.load_plugins()
    print("   🔌 Plugins loaded manually")
    
    # Check plugin features
    if fastjob.has_plugin_feature('dashboard'):
        print("   📊 Pro dashboard feature detected")
    else:
        print("   📦 Using Free edition (no Pro/Enterprise plugins)")
    
    print("\n✅ Demo completed!")
    print("\n💡 Key takeaways:")
    print("   • Plugins load automatically when you use FastJob")
    print("   • Use fastjob.testing utilities to control loading in tests")
    print("   • Context managers provide temporary control")
    print("   • Zero configuration needed for Pro/Enterprise upgrades")


def demo_embedded_worker():
    """Demonstrate plugin loading with embedded worker"""
    print("\n5️⃣ Embedded worker plugin loading:")
    print("-" * 38)
    
    import fastjob
    from fastjob.testing import disable_plugins, enable_plugins
    
    print("   🔄 Starting embedded worker (plugins will load automatically)")
    
    # Reset state
    from fastjob.testing import reset_plugin_state
    reset_plugin_state()
    
    try:
        # This would start the embedded worker and load plugins
        # (Commented out to avoid database requirements in demo)
        # fastjob.start_embedded_worker(run_once=True)
        print("   ✅ Embedded worker would load plugins automatically")
        print("   📦 Pro/Enterprise features would be available")
    except Exception as e:
        print(f"   ⚠️  Worker demo skipped: {e}")
    
    print("\n   🧪 Testing embedded worker without plugins:")
    disable_plugins()
    try:
        # This would start without loading plugins
        # fastjob.start_embedded_worker(run_once=True)  
        print("   ✅ Embedded worker would start without loading plugins")
        print("   📦 Only core features available in test")
    except Exception as e:
        print(f"   ⚠️  Worker test demo skipped: {e}")


if __name__ == "__main__":
    try:
        demo_automatic_loading()
        demo_embedded_worker()
        
        print("\n🎉 All demos completed successfully!")
        print("\n📚 For more information:")
        print("   • Core functionality: import fastjob")
        print("   • Pro features: pip install fastjob-pro")
        print("   • Enterprise features: pip install fastjob-enterprise")
        print("   • Testing: from fastjob.testing import disable_plugins, no_plugins")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        print("Make sure you have FastJob installed: pip install fastjob")