//go:build linux

package main

import (
	"context"
	"fmt"
	"os"

	"github.com/pkg/errors"
	"github.com/spf13/cobra"

	"github.com/repo-scm/git/mount"
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
	remoteRepo, localRepo := mount.ParsePath(ctx, manifestFile)

	if unmountPath != "" {
		if err := mount.UnmountOverlay(ctx, localRepo, unmountPath); err != nil {
			return errors.Wrap(err, "failed to unmount overlay\n")
		}
		if remoteRepo != "" {
			if err := mount.UnmountSshfs(ctx, localRepo); err != nil {
				return errors.Wrap(err, "failed to unmount sshfs\n")
			}
		}
		return nil
	}

	if remoteRepo != "" {
		if err := mount.MountSshfs(ctx, sshkeyFile, remoteRepo, localRepo); err != nil {
			return errors.Wrap(err, "failed to mount sshfs\n")
		}
	}

	if err := mount.MountOverlay(ctx, localRepo, mountPath); err != nil {
		return errors.Wrap(err, "failed to mount overlay\n")
	}

	return nil
}
