//go:build linux

package main

import (
	"context"
	"fmt"
	"os"
	"path"

	"github.com/pkg/errors"
	"github.com/spf13/cobra"

	git "github.com/repo-scm/git/mount"
)

var (
	BuildTime string
	CommitID  string
)

var (
	mountPath    string
	unmountPath  string
	manifestFile string
	sshkeyFile   string
)

var rootCmd = &cobra.Command{
	Use:     "repo",
	Short:   "repo with copy-on-write",
	Version: BuildTime + "-" + CommitID,
	Run: func(cmd *cobra.Command, args []string) {
		ctx := context.Background()
		if err := run(ctx); err != nil {
			_, _ = fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}
	},
}

// nolint:gochecknoinits
func init() {
	cobra.OnInitialize()

	rootCmd.PersistentFlags().StringVarP(&mountPath, "mount", "m", "", "mount path")
	rootCmd.PersistentFlags().StringVarP(&unmountPath, "unmount", "u", "", "unmount path")
	rootCmd.PersistentFlags().StringVarP(&manifestFile, "manifest", "n", "", "manifest file (user@host:/remote/manifest.xml:/local/manifest.xml)")
	rootCmd.PersistentFlags().StringVarP(&sshkeyFile, "sshkey", "s", "", "sshkey file (/path/to/id_rsa)")

	rootCmd.MarkFlagsOneRequired("mount", "unmount")
	rootCmd.MarkFlagsMutuallyExclusive("mount", "unmount")
	_ = rootCmd.MarkFlagRequired("manifest")

	rootCmd.Root().CompletionOptions.DisableDefaultCmd = true
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

func run(ctx context.Context) error {
	if unmountPath != "" {
		if err := unmount(ctx, unmountPath); err != nil {
			return errors.Wrap(err, "failed to unmount repo\n")
		}
		return nil
	}

	if err := mount(ctx, mountPath); err != nil {
		return errors.Wrap(err, "failed to mount repo\n")
	}

	return nil
}

func mount(ctx context.Context, root string) error {
	remoteManifest, localManifest := git.ParsePath(ctx, manifestFile)

	local := path.Dir(path.Clean(localManifest))

	if remoteManifest != "" {
		remote := path.Dir(path.Clean(remoteManifest))
		if err := git.MountSshfs(ctx, sshkeyFile, remote, local); err != nil {
			return errors.Wrap(err, "failed to mount sshfs\n")
		}
	}

	if err := git.MountOverlay(ctx, local, root); err != nil {
		return errors.Wrap(err, "failed to mount overlay\n")
	}

	return nil
}

func unmount(ctx context.Context, root string) error {
	remoteManifest, localManifest := git.ParsePath(ctx, manifestFile)

	local := path.Dir(path.Clean(localManifest))

	if err := git.UnmountOverlay(ctx, local, root); err != nil {
		return errors.Wrap(err, "failed to unmount overlay\n")
	}

	if remoteManifest != "" {
		if err := git.UnmountSshfs(ctx, local); err != nil {
			return errors.Wrap(err, "failed to unmount sshfs\n")
		}
	}

	return nil
}
