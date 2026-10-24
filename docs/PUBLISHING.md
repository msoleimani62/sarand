# Publishing to PyPI

sarand is published on PyPI as **`sarand-cli`** (the name `sarand` belongs to an
unrelated project). The command stays `sarand` and the import package stays
`sarand`. Publishing uses *trusted publishing*: GitHub proves its identity to
PyPI, so **no password or API token is stored anywhere**.

The workflow is `.github/workflows/release.yml`. It builds one wheel per
platform (Linux x86_64 and aarch64 for glibc and for musl/Alpine, macOS arm64
and x86_64, Windows x64; each works for every Python from 3.11 on) plus the
source distribution, checks that CI was green for the tagged commit, installs
the wheels of all seven platforms as a smoke test (the Linux aarch64, macOS
x86_64 and both Alpine ones natively, the Alpine ones inside a container),
publishes, and then
creates a GitHub Release with the wheels, the sdist and a `SHA256SUMS` file.

## One-time setup (about 20 minutes, all from a browser)

**1. Two accounts.** Create one on <https://pypi.org/account/register/> and one
on <https://test.pypi.org/account/register/> (they are separate sites with
separate accounts). Verify the email on both and turn on two-factor
authentication when asked (an authenticator app); PyPI requires it to publish.

**2. Register the project name on TestPyPI.** Open
<https://test.pypi.org/manage/account/publishing/>, section *Add a new pending
publisher*, tab *GitHub*, and fill in exactly:

| Field | Value |
|---|---|
| PyPI Project Name | `sarand-cli` |
| Owner | `msoleimani62` |
| Repository name | `sarand` |
| Workflow name | `release.yml` |
| Environment name | `testpypi` |

Press *Add*. A pending publisher does **not** reserve the name: the name is
claimed by the first successful upload.

**3. The same on PyPI.** Open <https://pypi.org/manage/account/publishing/> and
fill in the same fields, but *Environment name* = `pypi`.

**4. Two environments on GitHub.** In the repository: *Settings → Environments →
New environment*. Create `testpypi` (nothing else to set) and `pypi`. On `pypi`
tick *Required reviewers* and add yourself: every real release will then wait
for your approval before anything is uploaded.

## A dry run on TestPyPI

1. Repository → *Actions* → *Release* → *Run workflow* (branch `main`), tick
   *Also upload to TestPyPI*, run it.
2. Wait for the jobs: seven wheel builds, the sdist, the smoke tests. Then
   *Publish to TestPyPI* starts (no approval is needed for `testpypi`).
3. Open <https://test.pypi.org/project/sarand-cli/>: the page, the README and
   the files should be there.
4. Install it in a throwaway environment:

   ```bash
   python3 -m venv /tmp/try && /tmp/try/bin/pip install \
     -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple \
     sarand-cli && /tmp/try/bin/sarand --version
   ```

   (`--extra-index-url` lets the dependencies come from the real PyPI.)

A version can be uploaded to an index only once; the dry run uses
`skip-existing` so running it again does not fail.

## A real release

1. Make the release commit (CHANGELOG entry and version bump) and wait for CI
   to be green, exactly as for every release.
2. `python3 scripts/release.py tag && git push origin vX.Y.Z` creates and
   pushes the tag. The tag name must equal the version in `pyproject.toml`; the
   workflow refuses a tag that disagrees.
3. *Actions → Release*: when the builds are green, *Publish to PyPI* waits for
   your approval (*Review deployments → pypi → Approve*).
4. Open <https://pypi.org/project/sarand-cli/>, then verify:

   ```bash
   pipx install sarand-cli && sarand --version
   ```

Uploaded files can be *yanked* (hidden from resolvers) but never replaced or
deleted for reuse: a mistake is fixed by the next version.

## If something fails

| Symptom | Usual cause |
|---|---|
| `invalid-publisher` / "no matching publisher" | A field of the PyPI form differs from this repository: owner, repository, the workflow file name `release.yml`, or the environment name (`pypi` / `testpypi`). They are case-sensitive. |
| The name is rejected as taken | Someone registered `sarand-cli` before the first upload; choose another name and change `name` in `pyproject.toml` and the two forms. |
| `Publish` is skipped | A tag build needs a tag `v*`; the TestPyPI job needs the *Also upload to TestPyPI* box. |
| The `check` job fails on a tag | The tag does not equal `v` + the version in `pyproject.toml`. Delete the tag and re-tag after fixing the version. |
| A wheel build fails | Read that matrix job; the other platforms still finish (`fail-fast` is off), but nothing publishes until all builds and smoke tests pass. |
| `File already exists` | That version is on the index already; bump the version. |

The trusted-publisher form cannot name a *reusable* workflow: the publish jobs
must stay in `release.yml` itself.
