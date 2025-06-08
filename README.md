# repo

[![Build Status](https://github.com/repo-scm/repo/workflows/ci/badge.svg?branch=main&event=push)](https://github.com/repo-scm/repo/actions?query=workflow%3Aci)
[![Go Report Card](https://goreportcard.com/badge/github.com/repo-scm/repo)](https://goreportcard.com/report/github.com/repo-scm/repo)
[![License](https://img.shields.io/github/license/repo-scm/repo.svg)](https://github.com/repo-scm/repo/blob/main/LICENSE)
[![Tag](https://img.shields.io/github/tag/repo-scm/repo.svg)](https://github.com/repo-scm/repo/tags)



## Introduction

repo with copy-on-write



## Prerequisites

- Go >= 1.24.0



## Usage

```
```



## Example

### 1. Overlay

#### Mount

```bash
sudo ./repo --mount /mnt/overlay/repo --repository /path/to/repo

sudo chown -R $USER:$USER /mnt/overlay/repo
sudo chown -R $USER:$USER /path/to/cow-repo
```

#### Test

```bash
cd /mnt/overlay/repo

echo "new file" | tee newfile.txt
echo "modified" | tee README.md

git commit -m "repo changes"
git push origin main
```

#### Unmount

```bash
sudo ./repo --unmount /mnt/overlay/repo --repository /path/to/repo
```

#### Screenshot

![overlay](overlay.png)

### 2. SSHFS and Overlay

#### Config

```bash
cat $HOME/.ssh/config
```

```
Host *
    HostName <host>
    User <user>
    Port 22
    IdentityFile ~/.ssh/id_rsa
```

#### Mount

```bash
sudo ./repo --mount /mnt/overlay/repo --repository user@host:/remote/repo:/local/repo --sshkey /path/to/id_rsa

sudo chown -R $USER:$USER /mnt/overlay/repo
sudo chown -R $USER:$USER /path/to/cow-repo
```

#### Test

```bash
cd /mnt/overlay/repo

echo "new file" | tee newfile.txt
echo "modified" | tee README.md

git commit -m "repo changes"
git push origin main
```

#### Unmount

```bash
sudo ./repo --unmount /mnt/overlay/repo --repository /local/repo
```

#### Screenshot

![sshfs-overlay](sshfs-overlay.png)



## License

Project License can be found [here](LICENSE).



## Reference

- [cloud-native-build](https://docs.cnb.cool/zh/)
- [git-clone-yyds](https://cloud.tencent.com/developer/article/2456809)
- [git-clone-yyds](https://cnb.cool/cnb/cool/git-clone-yyds)
