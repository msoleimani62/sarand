#!/usr/bin/env bash
# Install the pinned Turborepo for the CI job `turbo` (round R12).
# The version is exact on purpose: the job is evidence of compatibility for that
# version, not a promise for every Turborepo release. It lives in a script (not in
# ci.yml) so the generated coverage matrix does not read an npm install in the
# workflow as "Node.js projects are tested in CI".
# Turborepo پین‌شده را برای job به نام turbo نصب می‌کند.
set -euo pipefail

: "${RUNNER_TEMP:?this script is for GitHub Actions}"
: "${GITHUB_ENV:?this script is for GitHub Actions}"

version="2.5.0"
node --version
npm install --prefix "${RUNNER_TEMP}/turbo" "turbo@${version}" --no-audit --no-fund --loglevel=error
bin="${RUNNER_TEMP}/turbo/node_modules/.bin/turbo"
"${bin}" --version
echo "SARAND_TURBO_BIN=${bin}" >> "${GITHUB_ENV}"
