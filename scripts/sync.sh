#!/bin/bash

# https://gist.github.com/craftslab/72bf50a05d047edff95dc2e13992c8b8

mkdir test-workspace

pushd test-workspace
#../repo init --partial-clone -b main -u $AOSP_MANIFEST --manifest-depth=1 -c --depth=1 -b main
#../repo sync -c -j4 --fail-fast
../repo init -u https://android.googlesource.com/platform/manifest
../repo sync --help
popd
