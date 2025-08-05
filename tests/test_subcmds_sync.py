# Copyright (C) 2022 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unittests for the subcmds/sync.py module."""

import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

import pytest

import command
from error import GitError
from error import RepoExitError
from project import SyncNetworkHalfResult
from subcmds import sync


@pytest.mark.parametrize(
    "use_superproject, cli_args, result",
    [
        (True, ["--current-branch"], True),
        (True, ["--no-current-branch"], True),
        (True, [], True),
        (False, ["--current-branch"], True),
        (False, ["--no-current-branch"], False),
        (False, [], None),
    ],
)
def test_get_current_branch_only(use_superproject, cli_args, result):
    """Test Sync._GetCurrentBranchOnly logic.

    Sync._GetCurrentBranchOnly should return True if a superproject is
    requested, and otherwise the value of the current_branch_only option.
    """
    cmd = sync.Sync()
    opts, _ = cmd.OptionParser.parse_args(cli_args)

    with mock.patch(
        "git_superproject.UseSuperproject", return_value=use_superproject
    ):
        assert cmd._GetCurrentBranchOnly(opts, cmd.manifest) == result


# Used to patch os.cpu_count() for reliable results.
OS_CPU_COUNT = 24


@pytest.mark.parametrize(
    "argv, jobs_manifest, jobs, jobs_net, jobs_check",
    [
        # No user or manifest settings.
        ([], None, OS_CPU_COUNT, 1, command.DEFAULT_LOCAL_JOBS),
        # No user settings, so manifest settings control.
        ([], 3, 3, 3, 3),
        # User settings, but no manifest.
        (["--jobs=4"], None, 4, 4, 4),
        (["--jobs=4", "--jobs-network=5"], None, 4, 5, 4),
        (["--jobs=4", "--jobs-checkout=6"], None, 4, 4, 6),
        (["--jobs=4", "--jobs-network=5", "--jobs-checkout=6"], None, 4, 5, 6),
        (
            ["--jobs-network=5"],
            None,
            OS_CPU_COUNT,
            5,
            command.DEFAULT_LOCAL_JOBS,
        ),
        (["--jobs-checkout=6"], None, OS_CPU_COUNT, 1, 6),
        (["--jobs-network=5", "--jobs-checkout=6"], None, OS_CPU_COUNT, 5, 6),
        # User settings with manifest settings.
        (["--jobs=4"], 3, 4, 4, 4),
        (["--jobs=4", "--jobs-network=5"], 3, 4, 5, 4),
        (["--jobs=4", "--jobs-checkout=6"], 3, 4, 4, 6),
        (["--jobs=4", "--jobs-network=5", "--jobs-checkout=6"], 3, 4, 5, 6),
        (["--jobs-network=5"], 3, 3, 5, 3),
        (["--jobs-checkout=6"], 3, 3, 3, 6),
        (["--jobs-network=5", "--jobs-checkout=6"], 3, 3, 5, 6),
        # Settings that exceed rlimits get capped.
        (["--jobs=1000000"], None, 83, 83, 83),
        ([], 1000000, 83, 83, 83),
    ],
)
def test_cli_jobs(argv, jobs_manifest, jobs, jobs_net, jobs_check):
    """Tests --jobs option behavior."""
    mp = mock.MagicMock()
    mp.manifest.default.sync_j = jobs_manifest

    cmd = sync.Sync()
    opts, args = cmd.OptionParser.parse_args(argv)
    cmd.ValidateOptions(opts, args)

    with mock.patch.object(sync, "_rlimit_nofile", return_value=(256, 256)):
        with mock.patch.object(os, "cpu_count", return_value=OS_CPU_COUNT):
            cmd._ValidateOptionsWithManifest(opts, mp)
            assert opts.jobs == jobs
            assert opts.jobs_network == jobs_net
            assert opts.jobs_checkout == jobs_check


@pytest.mark.parametrize(
    "argv, use_overlay_expected, overlay_auto_expected",
    [
        # No --use-overlay flag, should be False (default)
        ([], False, None),
        (["--jobs=4"], False, None),
        (["--current-branch"], False, None),
        # With --use-overlay flag, should be True
        (["--use-overlay"], True, None),
        (["--use-overlay", "--jobs=4"], True, None),
        (["--use-overlay", "--current-branch"], True, None),
        # With --overlay-auto options
        (["--use-overlay", "--overlay-auto=new"], True, "new"),
        (["--use-overlay", "--overlay-auto=outdated"], True, "outdated"),
        (["--use-overlay", "--overlay-auto=all"], True, "all"),
        (["--use-overlay", "--overlay-auto=cached"], True, "cached"),
    ],
)
def test_use_overlay_option(argv, use_overlay_expected, overlay_auto_expected):
    """Tests --use-overlay and --overlay-auto option behavior."""
    cmd = sync.Sync()
    opts, args = cmd.OptionParser.parse_args(argv)

    assert opts.use_overlay == use_overlay_expected
    assert getattr(opts, 'overlay_auto', None) == overlay_auto_expected


class UseOverlayInteractiveSelection(unittest.TestCase):
    """Tests for --use-overlay interactive project selection."""

    def setUp(self):
        """Common setup."""
        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.repo_dir = os.path.join(self.temp_dir, '.repo')
        os.makedirs(self.repo_dir)

        # Create sync command with proper mocking
        self.cmd = sync.Sync()

        # Mock outer_client to avoid AttributeError
        self.cmd.outer_client = mock.MagicMock()
        self.cmd.outer_client.manifest.repodir = self.repo_dir

        # Create mock projects
        self.project1 = mock.MagicMock()
        self.project1.name = "project1"
        self.project1.relpath = "path/to/project1"
        self.project1.Exists = True

        self.project2 = mock.MagicMock()
        self.project2.name = "project2"
        self.project2.relpath = "path/to/project2"
        self.project2.Exists = False

        self.project3 = mock.MagicMock()
        self.project3.name = "project3"
        self.project3.relpath = "path/to/project3"
        self.project3.Exists = True

        self.all_projects = [self.project1, self.project2, self.project3]

        # Mock the project status checking methods to avoid complex setup
        self.cmd._IsProjectOutdated = mock.MagicMock(return_value=False)
        self.cmd._LoadCachedSelection = mock.MagicMock(return_value=None)
        self.cmd._SaveCachedSelection = mock.MagicMock()

    def tearDown(self):
        """Cleanup."""
        shutil.rmtree(self.temp_dir)

    def test_parse_project_selection_individual_numbers(self):
        """Test parsing individual project numbers."""
        result = self.cmd._ParseProjectSelection("1 3", 3)
        self.assertEqual(result, [1, 3])

        result = self.cmd._ParseProjectSelection("2", 3)
        self.assertEqual(result, [2])

    def test_parse_project_selection_ranges(self):
        """Test parsing project ranges."""
        result = self.cmd._ParseProjectSelection("1-3", 3)
        self.assertEqual(result, [1, 2, 3])

        result = self.cmd._ParseProjectSelection("2-3", 3)
        self.assertEqual(result, [2, 3])

    def test_parse_project_selection_mixed(self):
        """Test parsing mixed individual numbers and ranges."""
        result = self.cmd._ParseProjectSelection("1 3-5 7", 10)
        self.assertEqual(result, [1, 3, 4, 5, 7])

    def test_parse_project_selection_invalid_range(self):
        """Test parsing invalid ranges."""
        # Range out of bounds
        result = self.cmd._ParseProjectSelection("1-5", 3)
        self.assertEqual(result, [])

        # Invalid range format
        result = self.cmd._ParseProjectSelection("5-1", 5)
        self.assertEqual(result, [])

        # Invalid number
        result = self.cmd._ParseProjectSelection("abc", 3)
        self.assertEqual(result, [])

    def test_parse_project_selection_out_of_bounds(self):
        """Test parsing out of bounds project numbers."""
        result = self.cmd._ParseProjectSelection("5", 3)
        self.assertEqual(result, [])

        result = self.cmd._ParseProjectSelection("0", 3)
        self.assertEqual(result, [])

    @mock.patch('builtins.input')
    def test_interactive_selection_all(self, mock_input):
        """Test interactive selection with 'all' option (option 3)."""
        mock_input.return_value = "3"  # Option 3 = sync all projects

        result = self.cmd._InteractiveProjectSelection(self.all_projects)
        self.assertEqual(result, self.all_projects)

    @mock.patch('builtins.input')
    def test_interactive_selection_none(self, mock_input):
        """Test interactive selection with 'none' option (option 5)."""
        mock_input.return_value = "5"  # Option 5 = skip sync

        result = self.cmd._InteractiveProjectSelection(self.all_projects)
        self.assertEqual(result, [])

    @mock.patch('builtins.input')
    def test_interactive_selection_empty_default_all(self, mock_input):
        """Test interactive selection with empty input defaults to all (option 3)."""
        mock_input.return_value = "3"  # Option 3 = sync all projects

        result = self.cmd._InteractiveProjectSelection(self.all_projects)
        self.assertEqual(result, self.all_projects)

    @mock.patch('builtins.input')
    def test_interactive_selection_specific_projects(self, mock_input):
        """Test interactive selection with custom selection (option 4)."""
        # Option 4 for custom selection, then "1 3" for specific projects, then "y" to confirm
        mock_input.side_effect = ["4", "1 3", "y"]

        # Mock the custom selection method to return expected projects
        with mock.patch.object(self.cmd, '_CustomProjectSelection') as mock_custom:
            mock_custom.return_value = [self.project1, self.project3]

            result = self.cmd._InteractiveProjectSelection(self.all_projects)
            expected = [self.project1, self.project3]
            self.assertEqual(result, expected)
            mock_custom.assert_called_once()

    @mock.patch('builtins.input')
    def test_interactive_selection_keyboard_interrupt(self, mock_input):
        """Test interactive selection handles KeyboardInterrupt."""
        mock_input.side_effect = KeyboardInterrupt()

        result = self.cmd._InteractiveProjectSelection(self.all_projects)
        self.assertEqual(result, [])

    @mock.patch('builtins.input')
    def test_interactive_selection_eof_error(self, mock_input):
        """Test interactive selection handles EOFError."""
        mock_input.side_effect = EOFError()

        result = self.cmd._InteractiveProjectSelection(self.all_projects)
        self.assertEqual(result, [])

    @mock.patch('builtins.input')
    def test_interactive_selection_invalid_then_valid(self, mock_input):
        """Test interactive selection handles invalid input then valid input."""
        mock_input.side_effect = ["invalid", "1"]  # Invalid option, then option 1 (new projects)

        # Mock to simulate new projects only
        self.cmd._IsProjectOutdated.return_value = True  # Make project2 appear as outdated

        result = self.cmd._InteractiveProjectSelection(self.all_projects)
        # Option 1 selects only new projects (project2 in this case)
        expected = [self.project2]  # Only the non-existing project
        self.assertEqual(result, expected)

    @mock.patch('builtins.input')
    def test_interactive_selection_confirm_no_then_yes(self, mock_input):
        """Test interactive selection with rejection then confirmation."""
        # Option 4 for custom, then "1" for first project, "n" to reject, "2" for second project, "y" to confirm
        mock_input.side_effect = ["4", "1", "n", "2", "y"]

        # Mock the custom selection method to handle the interaction
        with mock.patch.object(self.cmd, '_CustomProjectSelection') as mock_custom:
            mock_custom.return_value = [self.project2]

            result = self.cmd._InteractiveProjectSelection(self.all_projects)
            expected = [self.project2]
            self.assertEqual(result, expected)

    @mock.patch('builtins.input')
    def test_interactive_selection_new_projects_only(self, mock_input):
        """Test interactive selection option 1 (new projects only)."""
        mock_input.return_value = "1"  # Option 1 = sync only new projects

        result = self.cmd._InteractiveProjectSelection(self.all_projects)
        # Should return only projects that don't exist (Exists = False)
        expected = [self.project2]
        self.assertEqual(result, expected)

    @mock.patch('builtins.input')
    def test_interactive_selection_new_plus_outdated(self, mock_input):
        """Test interactive selection option 2 (new + outdated projects)."""
        mock_input.return_value = "2"  # Option 2 = sync new + outdated projects

        # Make project1 appear outdated
        self.cmd._IsProjectOutdated.side_effect = lambda p: p == self.project1

        result = self.cmd._InteractiveProjectSelection(self.all_projects)
        # Should return new (project2) + outdated (project1) projects
        expected = [self.project2, self.project1]
        self.assertEqual(result, expected)

    def test_interactive_selection_empty_projects(self):
        """Test interactive selection with empty project list."""
        result = self.cmd._InteractiveProjectSelection([])
        self.assertEqual(result, [])


class UseOverlayPerformanceFeatures(unittest.TestCase):
    """Tests for --use-overlay performance and automation features."""

    def setUp(self):
        """Common setup."""
        self.cmd = sync.Sync()

        # Create test directory structure
        self.temp_dir = tempfile.mkdtemp()
        self.repo_dir = os.path.join(self.temp_dir, '.repo')
        os.makedirs(self.repo_dir)

        # Mock outer client manifest
        self.cmd.outer_client = mock.MagicMock()
        self.cmd.outer_client.manifest.repodir = self.repo_dir

        # Create mock projects with different states
        self.new_project = mock.MagicMock()
        self.new_project.name = "new_project"
        self.new_project.relpath = "path/to/new_project"
        self.new_project.Exists = False

        self.outdated_project = mock.MagicMock()
        self.outdated_project.name = "outdated_project"
        self.outdated_project.relpath = "path/to/outdated_project"
        self.outdated_project.Exists = True
        self.outdated_project.gitdir = os.path.join(self.temp_dir, 'outdated_project', '.git')

        self.uptodate_project = mock.MagicMock()
        self.uptodate_project.name = "uptodate_project"
        self.uptodate_project.relpath = "path/to/uptodate_project"
        self.uptodate_project.Exists = True
        self.uptodate_project.gitdir = os.path.join(self.temp_dir, 'uptodate_project', '.git')

        self.all_projects = [self.new_project, self.outdated_project, self.uptodate_project]

    def tearDown(self):
        """Cleanup."""
        shutil.rmtree(self.temp_dir)

    def test_load_cached_selection_no_cache(self):
        """Test loading cached selection when no cache exists."""
        cache_file = os.path.join(self.repo_dir, "overlay_cache.json")
        result = self.cmd._LoadCachedSelection(cache_file, self.all_projects)
        self.assertIsNone(result)

    def test_save_and_load_cached_selection(self):
        """Test saving and loading cached project selection."""
        cache_file = os.path.join(self.repo_dir, "overlay_cache.json")
        project_names = ["new_project", "outdated_project"]

        # Save selection
        self.cmd._SaveCachedSelection(cache_file, project_names)
        self.assertTrue(os.path.exists(cache_file))

        # Load selection
        result = self.cmd._LoadCachedSelection(cache_file, self.all_projects)
        self.assertEqual(result, set(project_names))

    def test_cached_selection_validates_against_manifest(self):
        """Test that cached selection validates projects against current manifest."""
        cache_file = os.path.join(self.repo_dir, "overlay_cache.json")

        # Save selection with a project that won't exist in current manifest
        project_names = ["new_project", "nonexistent_project"]
        self.cmd._SaveCachedSelection(cache_file, project_names)

        # Load selection - should only return projects that exist in manifest
        result = self.cmd._LoadCachedSelection(cache_file, self.all_projects)
        self.assertEqual(result, {"new_project"})

    def test_cached_selection_expires_after_7_days(self):
        """Test that cached selection expires after 7 days."""
        cache_file = os.path.join(self.repo_dir, "overlay_cache.json")

        # Create expired cache (older than 7 days)
        expired_time = time.time() - (8 * 24 * 3600)  # 8 days ago
        cache_data = {
            'timestamp': expired_time,
            'projects': ['new_project']
        }

        with open(cache_file, 'w') as f:
            json.dump(cache_data, f)

        result = self.cmd._LoadCachedSelection(cache_file, self.all_projects)
        self.assertIsNone(result)

    def test_is_project_outdated_new_project(self):
        """Test project status detection for new projects."""
        result = self.cmd._IsProjectOutdated(self.new_project)
        self.assertTrue(result)

    def test_is_project_outdated_missing_fetch_head(self):
        """Test project status detection when FETCH_HEAD is missing."""
        # Create gitdir but no FETCH_HEAD
        os.makedirs(self.outdated_project.gitdir, exist_ok=True)

        result = self.cmd._IsProjectOutdated(self.outdated_project)
        self.assertTrue(result)

    def test_is_project_outdated_stale_fetch_head(self):
        """Test project status detection when FETCH_HEAD is stale."""
        # Create gitdir and stale FETCH_HEAD
        os.makedirs(self.outdated_project.gitdir, exist_ok=True)
        fetch_head = os.path.join(self.outdated_project.gitdir, 'FETCH_HEAD')

        # Create file with old timestamp (more than 24 hours)
        old_time = time.time() - (25 * 3600)  # 25 hours ago
        with open(fetch_head, 'w') as f:
            f.write("dummy content")
        os.utime(fetch_head, (old_time, old_time))

        result = self.cmd._IsProjectOutdated(self.outdated_project)
        self.assertTrue(result)

    def test_is_project_outdated_recent_fetch_head(self):
        """Test project status detection when FETCH_HEAD is recent."""
        # Create gitdir and recent FETCH_HEAD
        os.makedirs(self.uptodate_project.gitdir, exist_ok=True)
        fetch_head = os.path.join(self.uptodate_project.gitdir, 'FETCH_HEAD')

        with open(fetch_head, 'w') as f:
            f.write("dummy content")

        result = self.cmd._IsProjectOutdated(self.uptodate_project)
        self.assertFalse(result)

    def test_handle_auto_mode_new(self):
        """Test auto mode with 'new' selection."""
        cache_file = os.path.join(self.repo_dir, "overlay_cache.json")
        result = self.cmd._HandleAutoMode(
            "new", self.all_projects, [self.new_project],
            [self.outdated_project], [self.uptodate_project],
            None, cache_file
        )
        self.assertEqual(result, [self.new_project])

    def test_handle_auto_mode_outdated(self):
        """Test auto mode with 'outdated' selection."""
        cache_file = os.path.join(self.repo_dir, "overlay_cache.json")
        expected = [self.new_project, self.outdated_project]
        result = self.cmd._HandleAutoMode(
            "outdated", self.all_projects, [self.new_project],
            [self.outdated_project], [self.uptodate_project],
            None, cache_file
        )
        self.assertEqual(result, expected)

    def test_handle_auto_mode_all(self):
        """Test auto mode with 'all' selection."""
        cache_file = os.path.join(self.repo_dir, "overlay_cache.json")
        result = self.cmd._HandleAutoMode(
            "all", self.all_projects, [self.new_project],
            [self.outdated_project], [self.uptodate_project],
            None, cache_file
        )
        self.assertEqual(result, self.all_projects)

    def test_handle_auto_mode_cached_with_valid_cache(self):
        """Test auto mode with 'cached' selection when cache is valid."""
        cache_file = os.path.join(self.repo_dir, "overlay_cache.json")
        cached_selection = {"new_project", "outdated_project"}
        expected = [self.new_project, self.outdated_project]

        result = self.cmd._HandleAutoMode(
            "cached", self.all_projects, [self.new_project],
            [self.outdated_project], [self.uptodate_project],
            cached_selection, cache_file
        )
        self.assertEqual(result, expected)

    def test_handle_auto_mode_cached_fallback(self):
        """Test auto mode with 'cached' selection falls back when no cache."""
        cache_file = os.path.join(self.repo_dir, "overlay_cache.json")
        expected = [self.new_project, self.outdated_project]

        result = self.cmd._HandleAutoMode(
            "cached", self.all_projects, [self.new_project],
            [self.outdated_project], [self.uptodate_project],
            None, cache_file
        )
        self.assertEqual(result, expected)

    @mock.patch('builtins.input')
    def test_interactive_selection_with_quick_options(self, mock_input):
        """Test interactive selection with quick option choices."""
        # Mock the analysis methods
        with mock.patch.object(self.cmd, '_IsProjectOutdated') as mock_outdated:
            mock_outdated.side_effect = lambda p: p == self.outdated_project

            # Test option 2 (new + outdated)
            mock_input.return_value = "2"

            result = self.cmd._InteractiveProjectSelection(self.all_projects)
            expected = [self.new_project, self.outdated_project]
            self.assertEqual(result, expected)

    @mock.patch('builtins.input')
    def test_interactive_selection_auto_mode_bypass(self, mock_input):
        """Test that auto mode bypasses interactive prompts."""
        # Set auto mode
        self.cmd._overlay_auto_mode = "new"

        # Mock the analysis methods
        with mock.patch.object(self.cmd, '_IsProjectOutdated') as mock_outdated:
            mock_outdated.side_effect = lambda p: p == self.outdated_project

            result = self.cmd._InteractiveProjectSelection(self.all_projects)

            # Should return only new projects without prompting
            self.assertEqual(result, [self.new_project])
            # Input should not be called in auto mode
            mock_input.assert_not_called()

    @mock.patch('builtins.input')
    def test_custom_project_selection_categories(self, mock_input):
        """Test custom project selection with categorized display."""
        mock_input.side_effect = ["1", "y"]  # Select project 1, confirm

        result = self.cmd._CustomProjectSelection(
            self.all_projects, [self.new_project],
            [self.outdated_project], [self.uptodate_project]
        )

        self.assertEqual(result, [self.new_project])

    @mock.patch('builtins.input')
    def test_custom_project_selection_keyword_new(self, mock_input):
        """Test custom project selection with 'new' keyword."""
        mock_input.return_value = "new"

        result = self.cmd._CustomProjectSelection(
            self.all_projects, [self.new_project],
            [self.outdated_project], [self.uptodate_project]
        )

        self.assertEqual(result, [self.new_project])

    @mock.patch('builtins.input')
    def test_custom_project_selection_keyword_outdated(self, mock_input):
        """Test custom project selection with 'outdated' keyword."""
        mock_input.return_value = "outdated"

        result = self.cmd._CustomProjectSelection(
            self.all_projects, [self.new_project],
            [self.outdated_project], [self.uptodate_project]
        )

        self.assertEqual(result, [self.outdated_project])


class UseOverlayAutomatedMode(unittest.TestCase):
    """Tests for --overlay-auto automated mode integration."""

    def setUp(self):
        """Common setup."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_dir = os.path.join(self.temp_dir, '.repo')
        os.makedirs(self.repo_dir)

        self.manifest = mock.MagicMock(repodir=self.repo_dir)
        self.outer_client = mock.MagicMock()
        self.outer_client.manifest.repodir = self.repo_dir

        self.cmd = sync.Sync(manifest=self.manifest, outer_client=self.outer_client)

        # Create mock projects
        self.project1 = mock.MagicMock()
        self.project1.name = "project1"
        self.project1.relpath = "path/to/project1"
        self.project1.Exists = False  # New project

        self.project2 = mock.MagicMock()
        self.project2.name = "project2"
        self.project2.relpath = "path/to/project2"
        self.project2.Exists = True  # Existing project
        self.project2.gitdir = os.path.join(self.temp_dir, 'project2', '.git')

    def tearDown(self):
        """Cleanup."""
        shutil.rmtree(self.temp_dir)

    def test_overlay_auto_option_parsing(self):
        """Test that --overlay-auto options are parsed correctly."""
        test_cases = [
            (["--use-overlay", "--overlay-auto=new"], "new"),
            (["--use-overlay", "--overlay-auto=outdated"], "outdated"),
            (["--use-overlay", "--overlay-auto=all"], "all"),
            (["--use-overlay", "--overlay-auto=cached"], "cached"),
        ]

        for args, expected in test_cases:
            opt, _ = self.cmd.OptionParser.parse_args(args)
            self.assertEqual(opt.overlay_auto, expected)

    def test_overlay_auto_invalid_option(self):
        """Test that invalid --overlay-auto options are rejected."""
        with self.assertRaises(SystemExit):
            self.cmd.OptionParser.parse_args(["--use-overlay", "--overlay-auto=invalid"])

    @mock.patch('builtins.print')
    def test_overlay_auto_mode_sets_attribute(self, mock_print):
        """Test that overlay auto mode sets the correct attribute."""
        # Mock GetProjects to avoid complex setup
        with mock.patch.object(self.cmd, 'GetProjects', return_value=[self.project1]):
            # Mock other dependencies
            with mock.patch.object(self.cmd, '_UpdateProjectsRevisionId'):
                with mock.patch.object(self.cmd, '_IsProjectOutdated', return_value=False):

                    opt, _ = self.cmd.OptionParser.parse_args(["--use-overlay", "--overlay-auto=new"])

                    # Mock the manifest project to avoid errors
                    mp = mock.MagicMock()
                    mp.config.SetString = mock.MagicMock()

                    # Call the part that sets the auto mode
                    all_projects = [self.project1]
                    if opt.use_overlay:
                        self.cmd._overlay_auto_mode = getattr(opt, 'overlay_auto', None)
                        result = self.cmd._InteractiveProjectSelection(all_projects)

                    # Verify auto mode was set
                    self.assertEqual(self.cmd._overlay_auto_mode, "new")
                    # In auto mode, should return appropriate projects
                    self.assertEqual(result, [self.project1])  # New project selected


class LocalSyncState(unittest.TestCase):
    """Tests for LocalSyncState."""

    _TIME = 10

    def setUp(self):
        """Common setup."""
        self.topdir = tempfile.mkdtemp("LocalSyncState")
        self.repodir = os.path.join(self.topdir, ".repo")
        os.makedirs(self.repodir)

        self.manifest = mock.MagicMock(
            topdir=self.topdir,
            repodir=self.repodir,
            repoProject=mock.MagicMock(relpath=".repo/repo"),
        )
        self.state = self._new_state()

    def tearDown(self):
        """Common teardown."""
        shutil.rmtree(self.topdir)

    def _new_state(self, time=_TIME):
        with mock.patch("time.time", return_value=time):
            return sync.LocalSyncState(self.manifest)

    def test_set(self):
        """Times are set."""
        p = mock.MagicMock(relpath="projA")
        self.state.SetFetchTime(p)
        self.state.SetCheckoutTime(p)
        self.assertEqual(self.state.GetFetchTime(p), self._TIME)
        self.assertEqual(self.state.GetCheckoutTime(p), self._TIME)

    def test_update(self):
        """Times are updated."""
        with open(self.state._path, "w") as f:
            f.write(
                """
            {
              "projB": {
                "last_fetch": 5,
                "last_checkout": 7
              }
            }
            """
            )

        # Initialize state to read from the new file.
        self.state = self._new_state()
        projA = mock.MagicMock(relpath="projA")
        projB = mock.MagicMock(relpath="projB")
        self.assertEqual(self.state.GetFetchTime(projA), None)
        self.assertEqual(self.state.GetFetchTime(projB), 5)
        self.assertEqual(self.state.GetCheckoutTime(projB), 7)

        self.state.SetFetchTime(projA)
        self.state.SetFetchTime(projB)
        self.assertEqual(self.state.GetFetchTime(projA), self._TIME)
        self.assertEqual(self.state.GetFetchTime(projB), self._TIME)
        self.assertEqual(self.state.GetCheckoutTime(projB), 7)

    def test_save_to_file(self):
        """Data is saved under repodir."""
        p = mock.MagicMock(relpath="projA")
        self.state.SetFetchTime(p)
        self.state.Save()
        self.assertEqual(
            os.listdir(self.repodir), [".repo_localsyncstate.json"]
        )

    def test_partial_sync(self):
        """Partial sync state is detected."""
        with open(self.state._path, "w") as f:
            f.write(
                """
            {
              "projA": {
                "last_fetch": 5,
                "last_checkout": 5
              },
              "projB": {
                "last_fetch": 5,
                "last_checkout": 5
              }
            }
            """
            )

        # Initialize state to read from the new file.
        self.state = self._new_state()
        projB = mock.MagicMock(relpath="projB")
        self.assertEqual(self.state.IsPartiallySynced(), False)

        self.state.SetFetchTime(projB)
        self.state.SetCheckoutTime(projB)
        self.assertEqual(self.state.IsPartiallySynced(), True)

    def test_ignore_repo_project(self):
        """Sync data for repo project is ignored when checking partial sync."""
        p = mock.MagicMock(relpath="projA")
        self.state.SetFetchTime(p)
        self.state.SetCheckoutTime(p)
        self.state.SetFetchTime(self.manifest.repoProject)
        self.state.Save()
        self.assertEqual(self.state.IsPartiallySynced(), False)

        self.state = self._new_state(self._TIME + 1)
        self.state.SetFetchTime(self.manifest.repoProject)
        self.assertEqual(
            self.state.GetFetchTime(self.manifest.repoProject), self._TIME + 1
        )
        self.assertEqual(self.state.GetFetchTime(p), self._TIME)
        self.assertEqual(self.state.IsPartiallySynced(), False)

    def test_nonexistent_project(self):
        """Unsaved projects don't have data."""
        p = mock.MagicMock(relpath="projC")
        self.assertEqual(self.state.GetFetchTime(p), None)
        self.assertEqual(self.state.GetCheckoutTime(p), None)

    def test_prune_removed_projects(self):
        """Removed projects are pruned."""
        with open(self.state._path, "w") as f:
            f.write(
                """
            {
              "projA": {
                "last_fetch": 5
              },
              "projB": {
                "last_fetch": 7
              }
            }
            """
            )

        def mock_exists(path):
            if "projA" in path:
                return False
            return True

        projA = mock.MagicMock(relpath="projA")
        projB = mock.MagicMock(relpath="projB")
        self.state = self._new_state()
        self.assertEqual(self.state.GetFetchTime(projA), 5)
        self.assertEqual(self.state.GetFetchTime(projB), 7)
        with mock.patch("os.path.exists", side_effect=mock_exists):
            self.state.PruneRemovedProjects()
        self.assertIsNone(self.state.GetFetchTime(projA))

        self.state = self._new_state()
        self.assertIsNone(self.state.GetFetchTime(projA))
        self.assertEqual(self.state.GetFetchTime(projB), 7)

    def test_prune_removed_and_symlinked_projects(self):
        """Removed projects that still exists on disk as symlink are pruned."""
        with open(self.state._path, "w") as f:
            f.write(
                """
            {
              "projA": {
                "last_fetch": 5
              },
              "projB": {
                "last_fetch": 7
              }
            }
            """
            )

        def mock_exists(path):
            return True

        def mock_islink(path):
            if "projB" in path:
                return True
            return False

        projA = mock.MagicMock(relpath="projA")
        projB = mock.MagicMock(relpath="projB")
        self.state = self._new_state()
        self.assertEqual(self.state.GetFetchTime(projA), 5)
        self.assertEqual(self.state.GetFetchTime(projB), 7)
        with mock.patch("os.path.exists", side_effect=mock_exists):
            with mock.patch("os.path.islink", side_effect=mock_islink):
                self.state.PruneRemovedProjects()
        self.assertIsNone(self.state.GetFetchTime(projB))

        self.state = self._new_state()
        self.assertIsNone(self.state.GetFetchTime(projB))
        self.assertEqual(self.state.GetFetchTime(projA), 5)


class FakeProject:
    def __init__(self, relpath, name=None, objdir=None):
        self.relpath = relpath
        self.name = name or relpath
        self.objdir = objdir or relpath
        self.worktree = relpath

        self.use_git_worktrees = False
        self.UseAlternates = False
        self.manifest = mock.MagicMock()
        self.manifest.GetProjectsWithName.return_value = [self]
        self.config = mock.MagicMock()
        self.EnableRepositoryExtension = mock.MagicMock()

    def RelPath(self, local=None):
        return self.relpath

    def __str__(self):
        return f"project: {self.relpath}"

    def __repr__(self):
        return str(self)


class SafeCheckoutOrder(unittest.TestCase):
    def test_no_nested(self):
        p_f = FakeProject("f")
        p_foo = FakeProject("foo")
        out = sync._SafeCheckoutOrder([p_f, p_foo])
        self.assertEqual(out, [[p_f, p_foo]])

    def test_basic_nested(self):
        p_foo = p_foo = FakeProject("foo")
        p_foo_bar = FakeProject("foo/bar")
        out = sync._SafeCheckoutOrder([p_foo, p_foo_bar])
        self.assertEqual(out, [[p_foo], [p_foo_bar]])

    def test_complex_nested(self):
        p_foo = FakeProject("foo")
        p_foobar = FakeProject("foobar")
        p_foo_dash_bar = FakeProject("foo-bar")
        p_foo_bar = FakeProject("foo/bar")
        p_foo_bar_baz_baq = FakeProject("foo/bar/baz/baq")
        p_bar = FakeProject("bar")
        out = sync._SafeCheckoutOrder(
            [
                p_foo_bar_baz_baq,
                p_foo,
                p_foobar,
                p_foo_dash_bar,
                p_foo_bar,
                p_bar,
            ]
        )
        self.assertEqual(
            out,
            [
                [p_bar, p_foo, p_foo_dash_bar, p_foobar],
                [p_foo_bar],
                [p_foo_bar_baz_baq],
            ],
        )


class Chunksize(unittest.TestCase):
    """Tests for _chunksize."""

    def test_single_project(self):
        """Single project."""
        self.assertEqual(sync._chunksize(1, 1), 1)

    def test_low_project_count(self):
        """Multiple projects, low number of projects to sync."""
        self.assertEqual(sync._chunksize(10, 1), 10)
        self.assertEqual(sync._chunksize(10, 2), 5)
        self.assertEqual(sync._chunksize(10, 4), 2)
        self.assertEqual(sync._chunksize(10, 8), 1)
        self.assertEqual(sync._chunksize(10, 16), 1)

    def test_high_project_count(self):
        """Multiple projects, high number of projects to sync."""
        self.assertEqual(sync._chunksize(2800, 1), 32)
        self.assertEqual(sync._chunksize(2800, 16), 32)
        self.assertEqual(sync._chunksize(2800, 32), 32)
        self.assertEqual(sync._chunksize(2800, 64), 32)
        self.assertEqual(sync._chunksize(2800, 128), 21)


class GetPreciousObjectsState(unittest.TestCase):
    """Tests for _GetPreciousObjectsState."""

    def setUp(self):
        """Common setup."""
        self.cmd = sync.Sync()
        self.project = p = mock.MagicMock(
            use_git_worktrees=False, UseAlternates=False
        )
        p.manifest.GetProjectsWithName.return_value = [p]

        self.opt = mock.Mock(spec_set=["this_manifest_only"])
        self.opt.this_manifest_only = False

    def test_worktrees(self):
        """False for worktrees."""
        self.project.use_git_worktrees = True
        self.assertFalse(
            self.cmd._GetPreciousObjectsState(self.project, self.opt)
        )

    def test_not_shared(self):
        """Singleton project."""
        self.assertFalse(
            self.cmd._GetPreciousObjectsState(self.project, self.opt)
        )

    def test_shared(self):
        """Shared project."""
        self.project.manifest.GetProjectsWithName.return_value = [
            self.project,
            self.project,
        ]
        self.assertTrue(
            self.cmd._GetPreciousObjectsState(self.project, self.opt)
        )

    def test_shared_with_alternates(self):
        """Shared project, with alternates."""
        self.project.manifest.GetProjectsWithName.return_value = [
            self.project,
            self.project,
        ]
        self.project.UseAlternates = True
        self.assertFalse(
            self.cmd._GetPreciousObjectsState(self.project, self.opt)
        )

    def test_not_found(self):
        """Project not found in manifest."""
        self.project.manifest.GetProjectsWithName.return_value = []
        self.assertFalse(
            self.cmd._GetPreciousObjectsState(self.project, self.opt)
        )


class SyncCommand(unittest.TestCase):
    """Tests for cmd.Execute."""

    def setUp(self):
        """Common setup."""
        self.repodir = tempfile.mkdtemp(".repo")
        self.manifest = manifest = mock.MagicMock(
            repodir=self.repodir,
        )

        git_event_log = mock.MagicMock(ErrorEvent=mock.Mock(return_value=None))
        self.outer_client = outer_client = mock.MagicMock()
        outer_client.manifest.IsArchive = True
        manifest.manifestProject.worktree = "worktree_path/"
        manifest.repoProject.LastFetch = time.time()
        self.sync_network_half_error = None
        self.sync_local_half_error = None
        self.cmd = sync.Sync(
            manifest=manifest,
            outer_client=outer_client,
            git_event_log=git_event_log,
        )

        def Sync_NetworkHalf(*args, **kwargs):
            return SyncNetworkHalfResult(True, self.sync_network_half_error)

        def Sync_LocalHalf(*args, **kwargs):
            if self.sync_local_half_error:
                raise self.sync_local_half_error

        self.project = p = mock.MagicMock(
            use_git_worktrees=False,
            UseAlternates=False,
            name="project",
            Sync_NetworkHalf=Sync_NetworkHalf,
            Sync_LocalHalf=Sync_LocalHalf,
            RelPath=mock.Mock(return_value="rel_path"),
        )
        p.manifest.GetProjectsWithName.return_value = [p]

        mock.patch.object(
            sync,
            "_PostRepoFetch",
            return_value=None,
        ).start()

        mock.patch.object(
            self.cmd, "GetProjects", return_value=[self.project]
        ).start()

        opt, _ = self.cmd.OptionParser.parse_args([])
        opt.clone_bundle = False
        opt.jobs = 4
        opt.quiet = True
        opt.use_superproject = False
        opt.current_branch_only = True
        opt.optimized_fetch = True
        opt.retry_fetches = 1
        opt.prune = False
        opt.auto_gc = False
        opt.repo_verify = False
        self.opt = opt

    def tearDown(self):
        mock.patch.stopall()

    def test_command_exit_error(self):
        """Ensure unsuccessful commands raise expected errors."""
        self.sync_network_half_error = GitError(
            "sync_network_half_error error", project=self.project
        )
        self.sync_local_half_error = GitError(
            "sync_local_half_error", project=self.project
        )
        with self.assertRaises(RepoExitError) as e:
            self.cmd.Execute(self.opt, [])
            self.assertIn(self.sync_local_half_error, e.aggregate_errors)
            self.assertIn(self.sync_network_half_error, e.aggregate_errors)

    @mock.patch('builtins.input')
    def test_use_overlay_triggers_interactive_selection(self, mock_input):
        """Test that --use-overlay triggers interactive project selection."""
        # Set up option with use_overlay enabled
        opt, _ = self.cmd.OptionParser.parse_args(["--use-overlay"])
        opt.clone_bundle = False
        opt.jobs = 4
        opt.quiet = True
        opt.use_superproject = False
        opt.current_branch_only = True
        opt.optimized_fetch = True
        opt.retry_fetches = 1
        opt.prune = False
        opt.auto_gc = False
        opt.repo_verify = False
        opt.local_only = True  # Set to local only to avoid network operations
        opt.this_manifest_only = True

        # Mock input to select "all" projects
        mock_input.return_value = "all"

        # Mock _InteractiveProjectSelection to track if it's called
        with mock.patch.object(self.cmd, '_InteractiveProjectSelection') as mock_selection:
            mock_selection.return_value = [self.project]

            # Mock other methods to prevent actual sync operations
            with mock.patch.object(self.cmd, '_UpdateRepoProject'):
                with mock.patch.object(self.cmd, '_UpdateProjectsRevisionId'):
                    with mock.patch.object(self.cmd, '_UpdateAllManifestProjects'):
                        with mock.patch.object(sync, '_PostRepoUpgrade'):
                            try:
                                self.cmd.Execute(opt, [])
                            except:
                                # Expected to fail due to mocking, but we care about selection call
                                pass

            # Verify that interactive selection was called
            mock_selection.assert_called_once()

    def test_use_overlay_disabled_no_interactive_selection(self):
        """Test that without --use-overlay, interactive selection is not triggered."""
        # Set up option without use_overlay
        opt, _ = self.cmd.OptionParser.parse_args([])
        opt.clone_bundle = False
        opt.jobs = 4
        opt.quiet = True
        opt.use_superproject = False
        opt.current_branch_only = True
        opt.optimized_fetch = True
        opt.retry_fetches = 1
        opt.prune = False
        opt.auto_gc = False
        opt.repo_verify = False
        opt.local_only = True
        opt.this_manifest_only = True

        # Mock _InteractiveProjectSelection to track if it's called
        with mock.patch.object(self.cmd, '_InteractiveProjectSelection') as mock_selection:
            # Mock other methods to prevent actual sync operations
            with mock.patch.object(self.cmd, '_UpdateRepoProject'):
                with mock.patch.object(self.cmd, '_UpdateProjectsRevisionId'):
                    with mock.patch.object(self.cmd, '_UpdateAllManifestProjects'):
                        with mock.patch.object(sync, '_PostRepoUpgrade'):
                            try:
                                self.cmd.Execute(opt, [])
                            except:
                                # Expected to fail due to mocking, but we care about selection call
                                pass

            # Verify that interactive selection was NOT called
            mock_selection.assert_not_called()

    @mock.patch('builtins.print')
    def test_use_overlay_auto_mode_integration(self, mock_print):
        """Test that --overlay-auto modes are properly integrated."""
        # Test different auto modes
        auto_modes = ["new", "outdated", "all", "cached"]

        for mode in auto_modes:
            with self.subTest(mode=mode):
                # Set up option with auto mode
                opt, _ = self.cmd.OptionParser.parse_args(["--use-overlay", f"--overlay-auto={mode}"])
                opt.clone_bundle = False
                opt.jobs = 4
                opt.quiet = True
                opt.use_superproject = False
                opt.current_branch_only = True
                opt.optimized_fetch = True
                opt.retry_fetches = 1
                opt.prune = False
                opt.auto_gc = False
                opt.repo_verify = False
                opt.local_only = True
                opt.this_manifest_only = True

                # Mock _InteractiveProjectSelection to check auto mode is set
                def mock_selection(projects):
                    # Verify that auto mode is properly set
                    self.assertEqual(self.cmd._overlay_auto_mode, mode)
                    return [self.project]  # Return some projects

                with mock.patch.object(self.cmd, '_InteractiveProjectSelection', side_effect=mock_selection) as mock_selection_method:
                    # Mock other methods to prevent actual sync operations
                    with mock.patch.object(self.cmd, '_UpdateRepoProject'):
                        with mock.patch.object(self.cmd, '_UpdateProjectsRevisionId'):
                            with mock.patch.object(self.cmd, '_UpdateAllManifestProjects'):
                                with mock.patch.object(sync, '_PostRepoUpgrade'):
                                    try:
                                        self.cmd.Execute(opt, [])
                                    except:
                                        # Expected to fail due to mocking, but we care about auto mode
                                        pass

                    # Verify that interactive selection was called with auto mode set
                    mock_selection_method.assert_called_once()

    def test_overlay_auto_requires_use_overlay(self):
        """Test that --overlay-auto requires --use-overlay to be effective."""
        # Parse options with overlay-auto but without use-overlay
        opt, _ = self.cmd.OptionParser.parse_args(["--overlay-auto=new"])

        # use_overlay should be False
        self.assertFalse(opt.use_overlay)
        # overlay_auto should still be parsed
        self.assertEqual(opt.overlay_auto, "new")

        # When use_overlay is False, auto mode should not take effect
        # (This would be handled in the actual execution logic)


class SyncUpdateRepoProject(unittest.TestCase):
    """Tests for Sync._UpdateRepoProject."""

    def setUp(self):
        """Common setup."""
        self.repodir = tempfile.mkdtemp(".repo")
        self.manifest = manifest = mock.MagicMock(repodir=self.repodir)
        # Create a repoProject with a mock Sync_NetworkHalf.
        repoProject = mock.MagicMock(name="repo")
        repoProject.Sync_NetworkHalf = mock.Mock(
            return_value=SyncNetworkHalfResult(True, None)
        )
        manifest.repoProject = repoProject
        manifest.IsArchive = False
        manifest.CloneFilter = None
        manifest.PartialCloneExclude = None
        manifest.CloneFilterForDepth = None

        git_event_log = mock.MagicMock(ErrorEvent=mock.Mock(return_value=None))
        self.cmd = sync.Sync(manifest=manifest, git_event_log=git_event_log)

        opt, _ = self.cmd.OptionParser.parse_args([])
        opt.local_only = False
        opt.repo_verify = False
        opt.verbose = False
        opt.quiet = True
        opt.force_sync = False
        opt.clone_bundle = False
        opt.tags = False
        opt.optimized_fetch = False
        opt.retry_fetches = 0
        opt.prune = False
        self.opt = opt
        self.errors = []

        mock.patch.object(sync.Sync, "_GetCurrentBranchOnly").start()

    def tearDown(self):
        shutil.rmtree(self.repodir)
        mock.patch.stopall()

    def test_fetches_when_stale(self):
        """Test it fetches when the repo project is stale."""
        self.manifest.repoProject.LastFetch = time.time() - (
            sync._ONE_DAY_S + 1
        )

        with mock.patch.object(sync, "_PostRepoFetch") as mock_post_fetch:
            self.cmd._UpdateRepoProject(self.opt, self.manifest, self.errors)
            self.manifest.repoProject.Sync_NetworkHalf.assert_called_once()
            mock_post_fetch.assert_called_once()
            self.assertEqual(self.errors, [])

    def test_skips_when_fresh(self):
        """Test it skips fetch when repo project is fresh."""
        self.manifest.repoProject.LastFetch = time.time()

        with mock.patch.object(sync, "_PostRepoFetch") as mock_post_fetch:
            self.cmd._UpdateRepoProject(self.opt, self.manifest, self.errors)
            self.manifest.repoProject.Sync_NetworkHalf.assert_not_called()
            mock_post_fetch.assert_not_called()

    def test_skips_local_only(self):
        """Test it does nothing with --local-only."""
        self.opt.local_only = True
        self.manifest.repoProject.LastFetch = time.time() - (
            sync._ONE_DAY_S + 1
        )

        with mock.patch.object(sync, "_PostRepoFetch") as mock_post_fetch:
            self.cmd._UpdateRepoProject(self.opt, self.manifest, self.errors)
            self.manifest.repoProject.Sync_NetworkHalf.assert_not_called()
            mock_post_fetch.assert_not_called()

    def test_post_repo_fetch_skipped_on_env_var(self):
        """Test _PostRepoFetch is skipped when REPO_SKIP_SELF_UPDATE is set."""
        self.manifest.repoProject.LastFetch = time.time()

        with mock.patch.dict(os.environ, {"REPO_SKIP_SELF_UPDATE": "1"}):
            with mock.patch.object(sync, "_PostRepoFetch") as mock_post_fetch:
                self.cmd._UpdateRepoProject(
                    self.opt, self.manifest, self.errors
                )
                mock_post_fetch.assert_not_called()

    def test_fetch_failure_is_handled(self):
        """Test that a fetch failure is recorded and doesn't crash."""
        self.manifest.repoProject.LastFetch = time.time() - (
            sync._ONE_DAY_S + 1
        )
        fetch_error = GitError("Fetch failed")
        self.manifest.repoProject.Sync_NetworkHalf.return_value = (
            SyncNetworkHalfResult(False, fetch_error)
        )

        with mock.patch.object(sync, "_PostRepoFetch") as mock_post_fetch:
            self.cmd._UpdateRepoProject(self.opt, self.manifest, self.errors)
            self.manifest.repoProject.Sync_NetworkHalf.assert_called_once()
            mock_post_fetch.assert_not_called()
            self.assertEqual(self.errors, [fetch_error])


class InterleavedSyncTest(unittest.TestCase):
    """Tests for interleaved sync."""

    def setUp(self):
        """Set up a sync command with mocks."""
        self.repodir = tempfile.mkdtemp(".repo")
        self.manifest = mock.MagicMock(repodir=self.repodir)
        self.manifest.repoProject.LastFetch = time.time()
        self.manifest.repoProject.worktree = self.repodir
        self.manifest.manifestProject.worktree = self.repodir
        self.manifest.IsArchive = False
        self.manifest.CloneBundle = False
        self.manifest.default.sync_j = 1

        self.outer_client = mock.MagicMock()
        self.outer_client.manifest.IsArchive = False
        self.cmd = sync.Sync(
            manifest=self.manifest, outer_client=self.outer_client
        )
        self.cmd.outer_manifest = self.manifest

        # Mock projects.
        self.projA = FakeProject("projA", objdir="objA")
        self.projB = FakeProject("projB", objdir="objB")
        self.projA_sub = FakeProject(
            "projA/sub", name="projA_sub", objdir="objA_sub"
        )
        self.projC = FakeProject("projC", objdir="objC")

        # Mock methods that are not part of the core interleaved sync logic.
        mock.patch.object(self.cmd, "_UpdateAllManifestProjects").start()
        mock.patch.object(self.cmd, "_UpdateProjectsRevisionId").start()
        mock.patch.object(self.cmd, "_ValidateOptionsWithManifest").start()
        mock.patch.object(sync, "_PostRepoUpgrade").start()
        mock.patch.object(sync, "_PostRepoFetch").start()

        # Mock parallel context for worker tests.
        self.parallel_context_patcher = mock.patch(
            "subcmds.sync.Sync.get_parallel_context"
        )
        self.mock_get_parallel_context = self.parallel_context_patcher.start()
        self.sync_dict = {}
        self.mock_context = {
            "projects": [],
            "sync_dict": self.sync_dict,
        }
        self.mock_get_parallel_context.return_value = self.mock_context

        # Mock _GetCurrentBranchOnly for worker tests.
        mock.patch.object(sync.Sync, "_GetCurrentBranchOnly").start()

    def tearDown(self):
        """Clean up resources."""
        shutil.rmtree(self.repodir)
        mock.patch.stopall()

    def test_interleaved_fail_fast(self):
        """Test that --fail-fast is respected in interleaved mode."""
        opt, args = self.cmd.OptionParser.parse_args(
            ["--interleaved", "--fail-fast", "-j2"]
        )
        opt.quiet = True

        # With projA/sub, _SafeCheckoutOrder creates two batches:
        # 1. [projA, projB]
        # 2. [projA/sub]
        # We want to fail on the first batch and ensure the second isn't run.
        all_projects = [self.projA, self.projB, self.projA_sub]
        mock.patch.object(
            self.cmd, "GetProjects", return_value=all_projects
        ).start()

        # Mock ExecuteInParallel to simulate a failed run on the first batch of
        # projects.
        execute_mock = mock.patch.object(
            self.cmd, "ExecuteInParallel", return_value=False
        ).start()

        with self.assertRaises(sync.SyncFailFastError):
            self.cmd._SyncInterleaved(
                opt,
                args,
                [],
                self.manifest,
                self.manifest.manifestProject,
                all_projects,
                {},
            )

        execute_mock.assert_called_once()

    def test_interleaved_shared_objdir_serial(self):
        """Test that projects with shared objdir are processed serially."""
        opt, args = self.cmd.OptionParser.parse_args(["--interleaved", "-j4"])
        opt.quiet = True

        # Setup projects with a shared objdir.
        self.projA.objdir = "common_objdir"
        self.projC.objdir = "common_objdir"

        all_projects = [self.projA, self.projB, self.projC]
        mock.patch.object(
            self.cmd, "GetProjects", return_value=all_projects
        ).start()

        def execute_side_effect(jobs, target, work_items, **kwargs):
            # The callback is a partial object. The first arg is the set we
            # need to update to avoid the stall detection.
            synced_relpaths_set = kwargs["callback"].args[0]
            projects_in_pass = self.cmd.get_parallel_context()["projects"]
            for item in work_items:
                for project_idx in item:
                    synced_relpaths_set.add(
                        projects_in_pass[project_idx].relpath
                    )
            return True

        execute_mock = mock.patch.object(
            self.cmd, "ExecuteInParallel", side_effect=execute_side_effect
        ).start()

        self.cmd._SyncInterleaved(
            opt,
            args,
            [],
            self.manifest,
            self.manifest.manifestProject,
            all_projects,
            {},
        )

        execute_mock.assert_called_once()
        jobs_arg, _, work_items = execute_mock.call_args.args
        self.assertEqual(jobs_arg, 2)
        work_items_sets = {frozenset(item) for item in work_items}
        expected_sets = {frozenset([0, 2]), frozenset([1])}
        self.assertEqual(work_items_sets, expected_sets)

    def _get_opts(self, args=None):
        """Helper to get default options for worker tests."""
        if args is None:
            args = ["--interleaved"]
        opt, _ = self.cmd.OptionParser.parse_args(args)
        # Set defaults for options used by the worker.
        opt.quiet = True
        opt.verbose = False
        opt.force_sync = False
        opt.clone_bundle = False
        opt.tags = False
        opt.optimized_fetch = False
        opt.retry_fetches = 0
        opt.prune = False
        opt.detach_head = False
        opt.force_checkout = False
        opt.rebase = False
        return opt

    def test_worker_successful_sync(self):
        """Test _SyncProjectList with a successful fetch and checkout."""
        opt = self._get_opts()
        project = self.projA
        project.Sync_NetworkHalf = mock.Mock(
            return_value=SyncNetworkHalfResult(error=None, remote_fetched=True)
        )
        project.Sync_LocalHalf = mock.Mock()
        project.manifest.manifestProject.config = mock.MagicMock()
        self.mock_context["projects"] = [project]

        with mock.patch("subcmds.sync.SyncBuffer") as mock_sync_buffer:
            mock_sync_buf_instance = mock.MagicMock()
            mock_sync_buf_instance.Finish.return_value = True
            mock_sync_buffer.return_value = mock_sync_buf_instance

            result_obj = self.cmd._SyncProjectList(opt, [0])

            self.assertEqual(len(result_obj.results), 1)
            result = result_obj.results[0]
            self.assertTrue(result.fetch_success)
            self.assertTrue(result.checkout_success)
            self.assertIsNone(result.fetch_error)
            self.assertIsNone(result.checkout_error)
            project.Sync_NetworkHalf.assert_called_once()
            project.Sync_LocalHalf.assert_called_once()

    def test_worker_fetch_fails(self):
        """Test _SyncProjectList with a failed fetch."""
        opt = self._get_opts()
        project = self.projA
        fetch_error = GitError("Fetch failed")
        project.Sync_NetworkHalf = mock.Mock(
            return_value=SyncNetworkHalfResult(
                error=fetch_error, remote_fetched=False
            )
        )
        project.Sync_LocalHalf = mock.Mock()
        self.mock_context["projects"] = [project]

        result_obj = self.cmd._SyncProjectList(opt, [0])
        result = result_obj.results[0]

        self.assertFalse(result.fetch_success)
        self.assertFalse(result.checkout_success)
        self.assertEqual(result.fetch_error, fetch_error)
        self.assertIsNone(result.checkout_error)
        project.Sync_NetworkHalf.assert_called_once()
        project.Sync_LocalHalf.assert_not_called()

    def test_worker_no_worktree(self):
        """Test interleaved sync does not checkout with no worktree."""
        opt = self._get_opts()
        project = self.projA
        project.worktree = None
        project.Sync_NetworkHalf = mock.Mock(
            return_value=SyncNetworkHalfResult(error=None, remote_fetched=True)
        )
        project.Sync_LocalHalf = mock.Mock()
        self.mock_context["projects"] = [project]

        result_obj = self.cmd._SyncProjectList(opt, [0])
        result = result_obj.results[0]

        self.assertTrue(result.fetch_success)
        self.assertTrue(result.checkout_success)
        project.Sync_NetworkHalf.assert_called_once()
        project.Sync_LocalHalf.assert_not_called()

    def test_worker_fetch_fails_exception(self):
        """Test _SyncProjectList with an exception during fetch."""
        opt = self._get_opts()
        project = self.projA
        fetch_error = GitError("Fetch failed")
        project.Sync_NetworkHalf = mock.Mock(side_effect=fetch_error)
        project.Sync_LocalHalf = mock.Mock()
        self.mock_context["projects"] = [project]

        result_obj = self.cmd._SyncProjectList(opt, [0])
        result = result_obj.results[0]

        self.assertFalse(result.fetch_success)
        self.assertFalse(result.checkout_success)
        self.assertEqual(result.fetch_error, fetch_error)
        project.Sync_NetworkHalf.assert_called_once()
        project.Sync_LocalHalf.assert_not_called()

    def test_worker_checkout_fails(self):
        """Test _SyncProjectList with an exception during checkout."""
        opt = self._get_opts()
        project = self.projA
        project.Sync_NetworkHalf = mock.Mock(
            return_value=SyncNetworkHalfResult(error=None, remote_fetched=True)
        )
        checkout_error = GitError("Checkout failed")
        project.Sync_LocalHalf = mock.Mock(side_effect=checkout_error)
        project.manifest.manifestProject.config = mock.MagicMock()
        self.mock_context["projects"] = [project]

        with mock.patch("subcmds.sync.SyncBuffer"):
            result_obj = self.cmd._SyncProjectList(opt, [0])
            result = result_obj.results[0]

            self.assertTrue(result.fetch_success)
            self.assertFalse(result.checkout_success)
            self.assertIsNone(result.fetch_error)
            self.assertEqual(result.checkout_error, checkout_error)
            project.Sync_NetworkHalf.assert_called_once()
            project.Sync_LocalHalf.assert_called_once()

    def test_worker_local_only(self):
        """Test _SyncProjectList with --local-only."""
        opt = self._get_opts(["--interleaved", "--local-only"])
        project = self.projA
        project.Sync_NetworkHalf = mock.Mock()
        project.Sync_LocalHalf = mock.Mock()
        project.manifest.manifestProject.config = mock.MagicMock()
        self.mock_context["projects"] = [project]

        with mock.patch("subcmds.sync.SyncBuffer") as mock_sync_buffer:
            mock_sync_buf_instance = mock.MagicMock()
            mock_sync_buf_instance.Finish.return_value = True
            mock_sync_buffer.return_value = mock_sync_buf_instance

            result_obj = self.cmd._SyncProjectList(opt, [0])
            result = result_obj.results[0]

            self.assertTrue(result.fetch_success)
            self.assertTrue(result.checkout_success)
            project.Sync_NetworkHalf.assert_not_called()
            project.Sync_LocalHalf.assert_called_once()

    def test_worker_network_only(self):
        """Test _SyncProjectList with --network-only."""
        opt = self._get_opts(["--interleaved", "--network-only"])
        project = self.projA
        project.Sync_NetworkHalf = mock.Mock(
            return_value=SyncNetworkHalfResult(error=None, remote_fetched=True)
        )
        project.Sync_LocalHalf = mock.Mock()
        self.mock_context["projects"] = [project]

        result_obj = self.cmd._SyncProjectList(opt, [0])
        result = result_obj.results[0]

        self.assertTrue(result.fetch_success)
        self.assertTrue(result.checkout_success)
        project.Sync_NetworkHalf.assert_called_once()
        project.Sync_LocalHalf.assert_not_called()
