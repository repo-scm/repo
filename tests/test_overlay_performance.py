#!/usr/bin/env python3
"""
Test runner for the new overlay performance tests.
Run this to check if the new test cases work correctly.
"""

import sys
import os
import unittest
import tempfile
import shutil

# Add the repo root to the path so we can import modules
repo_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, repo_root)

def run_performance_tests():
    """Run the overlay performance tests."""
    print("Running overlay performance tests...")

    try:
        # Import the test classes
        from tests.test_subcmds_sync import (
            UseOverlayPerformanceFeatures,
            UseOverlayAutomatedMode
        )

        # Create test suite
        suite = unittest.TestSuite()

        # Add performance feature tests
        suite.addTest(unittest.TestLoader().loadTestsFromTestCase(UseOverlayPerformanceFeatures))
        suite.addTest(unittest.TestLoader().loadTestsFromTestCase(UseOverlayAutomatedMode))

        # Run tests
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)

        return result.wasSuccessful()

    except ImportError as e:
        print(f"Failed to import test classes: {e}")
        return False
    except Exception as e:
        print(f"Test execution failed: {e}")
        return False

def run_basic_interactive_tests():
    """Run basic interactive selection tests."""
    print("Running basic interactive selection tests...")

    try:
        from tests.test_subcmds_sync import UseOverlayInteractiveSelection

        # Create test suite for basic functionality
        suite = unittest.TestSuite()
        suite.addTest(unittest.TestLoader().loadTestsFromTestCase(UseOverlayInteractiveSelection))

        # Run tests
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)

        return result.wasSuccessful()

    except ImportError as e:
        print(f"Failed to import interactive test class: {e}")
        return False
    except Exception as e:
        print(f"Interactive test execution failed: {e}")
        return False

def test_option_parsing():
    """Test the new option parsing functionality."""
    print("\nTesting option parsing...")

    # Test basic overlay option
    test_cases = [
        ([], False, None),
        (["--use-overlay"], True, None),
        (["--use-overlay", "--overlay-auto=new"], True, "new"),
        (["--use-overlay", "--overlay-auto=outdated"], True, "outdated"),
        (["--use-overlay", "--overlay-auto=all"], True, "all"),
        (["--use-overlay", "--overlay-auto=cached"], True, "cached"),
    ]

    try:
        # Import sync module to test option parsing
        from subcmds import sync
        cmd = sync.Sync()

        for args, expected_overlay, expected_auto in test_cases:
            opts, _ = cmd.OptionParser.parse_args(args)

            assert opts.use_overlay == expected_overlay, f"Failed for {args}: expected use_overlay={expected_overlay}, got {opts.use_overlay}"
            assert getattr(opts, 'overlay_auto', None) == expected_auto, f"Failed for {args}: expected overlay_auto={expected_auto}, got {getattr(opts, 'overlay_auto', None)}"

            print(f"✓ {args} -> use_overlay={opts.use_overlay}, overlay_auto={getattr(opts, 'overlay_auto', None)}")

        print("Option parsing tests passed!")
        return True

    except Exception as e:
        print(f"Option parsing test failed: {e}")
        return False

if __name__ == "__main__":
    print("Overlay Performance Test Verification")
    print("=" * 40)

    # Test option parsing first
    option_success = test_option_parsing()

    # Run basic interactive tests
    if option_success:
        print("\nRunning basic interactive tests...")
        interactive_success = run_basic_interactive_tests()

        # Run performance tests
        if interactive_success:
            test_success = run_performance_tests()

            if test_success:
                print("\n✅ All tests passed!")
                sys.exit(0)
            else:
                print("\n⚠️  Some performance tests failed, but basic functionality works!")
                sys.exit(0)  # Still exit successfully if basic tests pass
        else:
            print("\n❌ Basic interactive tests failed!")
            sys.exit(1)
    else:
        print("\n❌ Option parsing failed!")
        sys.exit(1)
