# Overlay Tests for 'repo sync --use-overlay'

## Overview
Updated `test_subcmds_sync.py` with comprehensive test coverage for the new `--use-overlay` performance features and automated mode functionality.

## New Test Classes Added

### 1. `UseOverlayPerformanceFeatures`
Tests for caching, project categorization, and performance optimizations:

#### Caching Tests
- `test_load_cached_selection_no_cache()` - No cache file exists
- `test_save_and_load_cached_selection()` - Save and load cache functionality
- `test_cached_selection_validates_against_manifest()` - Cache validation
- `test_cached_selection_expires_after_7_days()` - Cache expiration

#### Project Status Detection Tests
- `test_is_project_outdated_new_project()` - New project detection
- `test_is_project_outdated_missing_fetch_head()` - Missing FETCH_HEAD
- `test_is_project_outdated_stale_fetch_head()` - Stale FETCH_HEAD (>24h)
- `test_is_project_outdated_recent_fetch_head()` - Recent FETCH_HEAD

#### Auto Mode Handler Tests
- `test_handle_auto_mode_new()` - Auto select new projects
- `test_handle_auto_mode_outdated()` - Auto select new + outdated
- `test_handle_auto_mode_all()` - Auto select all projects
- `test_handle_auto_mode_cached_with_valid_cache()` - Use cached selection
- `test_handle_auto_mode_cached_fallback()` - Fallback when no cache

#### Interactive Selection Tests
- `test_interactive_selection_with_quick_options()` - Quick option selection
- `test_interactive_selection_auto_mode_bypass()` - Auto mode bypasses prompts
- `test_custom_project_selection_categories()` - Categorized display
- `test_custom_project_selection_keyword_new()` - "new" keyword
- `test_custom_project_selection_keyword_outdated()` - "outdated" keyword

### 2. `UseOverlayAutomatedMode`
Tests for `--overlay-auto` option integration:

#### Option Parsing Tests
- `test_overlay_auto_option_parsing()` - Valid options parsed correctly
- `test_overlay_auto_invalid_option()` - Invalid options rejected

#### Integration Tests
- `test_overlay_auto_mode_sets_attribute()` - Auto mode attribute setting

## Updated Existing Tests

### 1. `test_use_overlay_option()`
Enhanced parametrized test to include `--overlay-auto` options:
- Tests all combinations of `--use-overlay` and `--overlay-auto`
- Validates both `use_overlay` and `overlay_auto` attributes

### 2. `SyncCommand` class
Added new test methods:
- `test_use_overlay_auto_mode_integration()` - Integration with Execute method
- `test_overlay_auto_requires_use_overlay()` - Option dependency validation

## Test Coverage

### Functionality Covered
✅ Option parsing for `--overlay-auto`
✅ Cache file creation, loading, and validation
✅ Cache expiration (7-day timeout)
✅ Project categorization (new, outdated, up-to-date)
✅ Project status detection logic
✅ Auto mode selection algorithms
✅ Interactive mode bypass in auto mode
✅ Integration with main Execute() method
✅ Error handling and fallbacks
✅ Custom selection with keywords

### Edge Cases Covered
✅ Missing cache files
✅ Expired cache files
✅ Invalid cached project names
✅ Missing FETCH_HEAD files
✅ Stale vs recent FETCH_HEAD timestamps
✅ Empty project lists
✅ Invalid auto mode options
✅ Auto mode without use_overlay flag

## Running the Tests

### Run all overlay tests:
```bash
python -m pytest tests/test_subcmds_sync.py::UseOverlayPerformanceFeatures -v
python -m pytest tests/test_subcmds_sync.py::UseOverlayAutomatedMode -v
```

### Run specific test:
```bash
python -m pytest tests/test_subcmds_sync.py::UseOverlayPerformanceFeatures::test_save_and_load_cached_selection -v
```

### Quick verification:
```bash
python tests/test_overlay_performance.py
```

## Files Modified
- `tests/test_subcmds_sync.py` - Added comprehensive test coverage
- Added `json` import for cache testing
- Enhanced existing parametrized tests
- Added new test classes with 20+ test methods

## Key Testing Features
1. **Mocking Strategy**: Uses `mock.MagicMock()` for projects and filesystem operations
2. **Temporary Directories**: Creates real temporary directories for cache testing
3. **Time Simulation**: Mocks time functions for cache expiration testing
4. **Parametrized Tests**: Uses `@pytest.mark.parametrize` for option combinations
5. **Integration Testing**: Tests integration with main Execute() method
6. **Error Path Testing**: Covers error conditions and fallback scenarios

This comprehensive test suite ensures the reliability and correctness of all new performance features and automated modes for the `--use-overlay` functionality.
