//go:build linux

package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path"
	"regexp"
	"strings"
	"syscall"

	"github.com/pkg/errors"
	"github.com/spf13/cobra"
)

const (
	directoryPerm = 0755
)

var (
	BuildTime string
	CommitID  string
)

var (
	mountPath      string
	unmountPath    string
	repositoryPath string
	sshkeyFile     string

	sshfsMount string
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
	rootCmd.PersistentFlags().StringVarP(&repositoryPath, "repository", "r", "", "repository path (user@host:/remote/repo:/local/repo)")
	rootCmd.PersistentFlags().StringVarP(&sshkeyFile, "sshkey", "s", "", "sshkey file (/path/to/id_rsa)")

	rootCmd.MarkFlagsOneRequired("mount", "unmount")
	rootCmd.MarkFlagsMutuallyExclusive("mount", "unmount")
	_ = rootCmd.MarkFlagRequired("repository")

	rootCmd.Root().CompletionOptions.DisableDefaultCmd = true
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

func run(ctx context.Context) error {
	remoteRepo, localRepo := parsePath(ctx, repositoryPath)

	if unmountPath != "" {
		if err := unmountOverlay(ctx, localRepo, unmountPath); err != nil {
			return errors.Wrap(err, "failed to unmount overlay\n")
		}
		if remoteRepo != "" {
			if err := unmountSshfs(ctx, localRepo); err != nil {
				return errors.Wrap(err, "failed to unmount sshfs\n")
			}
		}
		return nil
	}

	if remoteRepo != "" {
		if err := mountSshfs(ctx, sshkeyFile, remoteRepo, localRepo); err != nil {
			return errors.Wrap(err, "failed to mount sshfs\n")
		}
	}

	if err := mountOverlay(ctx, localRepo, mountPath); err != nil {
		return errors.Wrap(err, "failed to mount overlay\n")
	}

	return nil
}

func parsePath(_ context.Context, name string) (remote, local string) {
	// Remote format: user@host:/remote/repo:/local/repo
	remotePattern := `^([^@]+)@([^:]+):([^:]+):([^:]+)$`
	remoteRegex := regexp.MustCompile(remotePattern)

	if matches := remoteRegex.FindStringSubmatch(name); matches != nil {
		_path := strings.Split(name, ":")
		return _path[0] + ":" + _path[1], _path[2]
	}

	return "", name
}

func mountSshfs(_ context.Context, key, remote, local string) error {
	if remote == "" || local == "" {
		return errors.New("remote and local are required\n")
	}

	if err := os.MkdirAll(local, directoryPerm); err != nil {
		return errors.Wrap(err, "failed to make directory\n")
	}

	cmd := exec.Command("sshfs",
		remote,
		path.Clean(local),
		"-o", "allow_other",
		"-o", "default_permissions",
		"-o", "follow_symlinks",
		"-o", fmt.Sprintf("IdentityFile=%s,StrictHostKeyChecking=no,UserKnownHostsFile=/dev/null,port=22", path.Clean(key)),
	)

	if err := cmd.Run(); err != nil {
		return errors.Wrap(err, "failed to mount sshfs\n")
	}

	fmt.Printf("\nSuccessfully mounted sshfs at %s\n", sshfsMount)

	return nil
}

func unmountSshfs(_ context.Context, local string) error {
	if local == "" {
		return errors.New("local is required\n")
	}

	defer func(path string) {
		_ = os.RemoveAll(path)
	}(local)

	cmd := exec.Command("fusermount", "-u", path.Clean(local))

	if err := cmd.Run(); err != nil {
		return errors.Wrap(err, "failed to unmount sshfs\n")
	}

	return nil
}

func mountOverlay(_ context.Context, repo, mount string) error {
	if repo == "" || mount == "" {
		return errors.New("repo and mount are required\n")
	}

	repoDir := path.Dir(path.Clean(repo))

	mountDir := path.Dir(path.Clean(mount))
	mountName := path.Base(path.Clean(mount))

	upperPath := path.Join(repoDir, "cow-"+mountName)
	workPath := path.Join(mountDir, "work-"+mountName)

	dirs := []string{mount, upperPath, workPath}

	for _, item := range dirs {
		if err := os.MkdirAll(item, directoryPerm); err != nil {
			return errors.Wrap(err, "failed to make directory\n")
		}
	}

	opts := fmt.Sprintf("lowerdir=%s,upperdir=%s,workdir=%s,index=off", repo, upperPath, workPath)

	if err := syscall.Mount("overlay", mount, "overlay", 0, opts); err != nil {
		return errors.Wrap(err, "failed to mount overlay\n")
	}

	fmt.Printf("\nSuccessfully mounted overlay at %s\n", upperPath)

	return nil
}

func unmountOverlay(_ context.Context, repo, unmount string) error {
	if repo == "" || unmount == "" {
		return errors.New("repo and unmount are required\n")
	}

	unmountDir := path.Dir(path.Clean(unmount))
	unmountName := path.Base(path.Clean(unmount))

	repoPath := path.Dir(path.Clean(repo))
	upperPath := path.Join(repoPath, "cow-"+unmountName)
	workPath := path.Join(unmountDir, "work-"+unmountName)

	defer func(unmount, workPath, upperPath string) {
		_ = os.RemoveAll(unmount)
		_ = os.RemoveAll(workPath)
		_ = os.RemoveAll(upperPath)
	}(unmount, workPath, upperPath)

	if err := syscall.Unmount(unmount, 0); err != nil {
		return errors.Wrap(err, "failed to unmount overlay\n")
	}

	fmt.Printf("\nSuccessfully unmounted overlay\n")

	return nil
}
