#!/usr/bin/env python3
"""
FastJob Test Runner - Runs tests in organized batches with API isolation

This script runs tests in the new isolated structure:
- Global API tests: Use fastjob.job, fastjob.enqueue, etc.
- Instance API tests: Use app = FastJob(), app.job, etc.  
- Infrastructure tests: Test underlying systems (CLI, connections, etc.)
- Unit tests: Test individual modules
"""
import subprocess
import sys
import os


def run_test_batch(name, test_paths, verbose=True):
    """Run a batch of tests and return success status"""
    print(f"\n{'='*60}")
    print(f"Running {name}")
    print(f"{'='*60}")

    cmd = ["python3", "-m", "pytest"] + test_paths
    if verbose:
        cmd.append("-v")
    else:
        cmd.extend(["--tb=no", "-q"])

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print(f"✅ {name} - ALL PASSED")
        return True
    else:
        print(f"❌ {name} - FAILED")
        return False


def main():
    """Run all test batches with new API isolation structure"""
    print("🚀 FastJob Comprehensive Test Suite")
    print("Running tests with API isolation for maximum reliability...")

    # Change to the script's directory (should be the fastjob root)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"📁 Running tests from: {script_dir}")

    # Define test batches with new structure
    test_batches = [
        # GLOBAL API TESTS - Use fastjob.job, fastjob.enqueue, etc.
        (
            "Global API - Job Management & Introspection",
            ["tests/integration/global_api/test_job_introspection.py"],
        ),
        (
            "Global API - Corrupted Data Handling",
            ["tests/integration/global_api/test_corrupted_data_handling.py"],
        ),
        (
            "Global API - Edge Cases",
            ["tests/integration/global_api/test_edge_cases.py"],
        ),
        (
            "Global API - Error Handling Edge Cases",
            ["tests/integration/global_api/test_error_handling_edge_cases.py"],
        ),
        (
            "Global API - Embedded Worker System",
            ["tests/integration/global_api/test_embedded_worker.py"],
        ),
        (
            "Global API - Production Scenarios",
            ["tests/integration/global_api/test_production_scenarios.py"],
        ),
        (
            "Global API - Scheduling & Timing",
            ["tests/integration/global_api/test_scheduling.py"],
        ),
        (
            "Global API - Specification Compliance",
            ["tests/integration/global_api/test_specification_compliance.py"],
        ),
        (
            "Global API - TTL & Job Cleanup",
            ["tests/integration/global_api/test_ttl_functionality.py"],
        ),
        
        # INSTANCE API TESTS - Use app = FastJob(), app.job, etc.
        (
            "Instance API - Core Functionality",
            ["tests/integration/instance_api/test_core.py"],
        ),
        (
            "Instance API - Worker Heartbeat System",
            ["tests/integration/instance_api/test_worker_heartbeat.py"],
        ),
        (
            "Instance API - Worker Heartbeat Comprehensive",
            ["tests/integration/instance_api/test_worker_heartbeat_comprehensive.py"],
        ),
        
        # INFRASTRUCTURE TESTS - Support both APIs
        (
            "Infrastructure - CLI Integration",
            [
                "tests/integration/infrastructure/test_cli_integration.py",
                "tests/integration/infrastructure/test_cli_queue_behavior.py",
                "tests/integration/infrastructure/test_complete_cli_plugin_integration.py",
            ],
        ),
        (
            "Infrastructure - Database URL Integration",
            ["tests/integration/test_database_url_integration.py"],
        ),
        (
            "Infrastructure - Connection Context",
            ["tests/integration/infrastructure/test_connection_context.py"],
        ),
        (
            "Infrastructure - LISTEN/NOTIFY Performance", 
            ["tests/integration/infrastructure/test_listen_notify.py"],
        ),
        (
            "Infrastructure - Queue Processing Behavior",
            ["tests/integration/infrastructure/test_queue_processing_behavior.py"],
        ),
        
        # UNIT TESTS
        (
            "Unit Tests - Core Modules",
            [
                "tests/unit/test_health.py",
                "tests/unit/test_errors.py",
                "tests/unit/test_hashing.py",
            ],
        ),
        (
            "Unit Tests - Other",
            [
                "tests/unit/test_cli_plugin_system.py",
                "tests/unit/test_configuration.py",
                "tests/unit/test_plugin_loading_control.py",
                "tests/unit/test_global_api.py",
            ],
        ),
    ]

    # Run each batch
    results = []
    total_batches = len(test_batches)

    for i, (name, paths) in enumerate(test_batches, 1):
        print(f"\n[{i}/{total_batches}] ", end="")
        success = run_test_batch(name, paths, verbose=False)
        results.append((name, success))

    # Summary
    print(f"\n{'='*60}")
    print("🎯 FINAL RESULTS")
    print(f"{'='*60}")

    passed_count = 0
    for name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status:12} {name}")
        if success:
            passed_count += 1

    print(f"\n📊 SUMMARY: {passed_count}/{total_batches} test batches passed")

    if passed_count == total_batches:
        print("🎉 ALL TESTS PASSING! FastJob is ready for production! 🚀")
        return 0
    else:
        print("⚠️  Some test batches failed. Check individual results above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
