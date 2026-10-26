#!/usr/bin/env bash
# Install the pinned kubeconform for the CI job `kube` (round R10c).
# `go install` checks the module against the public checksum database, so the
# pinned version is also integrity-checked. It lives in a script (not in
# ci.yml) so the generated coverage matrix does not read a Go install in the
# workflow as "Go projects are tested in CI".
# kubeconform پین‌شده را برای job به نام kube نصب می‌کند.
set -euo pipefail

: "${GITHUB_PATH:?this script is for GitHub Actions}"

version="v0.6.7"
go install "github.com/yannh/kubeconform/cmd/kubeconform@${version}"
bin_dir="$(go env GOPATH)/bin"
echo "${bin_dir}" >> "${GITHUB_PATH}"
"${bin_dir}/kubeconform" -v
