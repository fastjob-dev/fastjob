#!/usr/bin/env python3
"""
FastJob Test Runner - Runs tests in organized batches to ensure stability

This script runs tests in smaller, logical groups to avoid test isolation issues
while ensuring all functionality is properly tested.
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
    """Run all test batches"""
    print("🚀 FastJob Comprehensive Test Suite")
    print("Running tests in organized batches for maximum reliability...")
    
    # Change to the script's directory (should be the fastjob root)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"📁 Running tests from: {script_dir}")
    
    # Define test batches
    test_batches = [
        ("Core Functionality", [
            "tests/integration/test_core.py",
            "tests/integration/test_connection_context.py", 
            "tests/integration/test_edge_cases.py"
        ]),
        
        ("CLI Integration", [
            "tests/integration/test_cli_integration.py",
            "tests/integration/test_complete_cli_plugin_integration.py"
        ]),
        
        ("Job Management & Introspection", [
            "tests/integration/test_job_introspection.py"
        ]),
        
        ("Embedded Worker System", [
            "tests/integration/test_embedded_worker.py"
        ]),
        
        ("Production Scenarios", [
            "tests/integration/test_production_scenarios.py"
        ]),
        
        ("Scheduling & Timing", [
            "tests/integration/test_scheduling.py"
        ]),
        
        ("Specification Compliance", [
            "tests/integration/test_specification_compliance.py"
        ]),
        
        ("Unit Tests", [
            "tests/unit/"
        ])
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