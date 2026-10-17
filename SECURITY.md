# Security policy

## Supported versions

Only the latest release on PyPI (`sarand-cli`) receives security fixes. sarand
is maintained by one person, so the response times below are goals, not
guarantees.

## Reporting a vulnerability

Please report privately, not in a public issue.

1. Open the repository's **Security** tab and choose **Report a vulnerability**
   (GitHub private vulnerability reporting):
   <https://github.com/msoleimani62/sarand/security/advisories/new>
2. If that option is not available, open a public issue titled
   `Security contact request` **without any details** and ask for a private
   channel.

Include the sarand version (`sarand --version`), your operating system, what
you did, what you expected and what happened. A minimal project that
reproduces it helps most. Please do not include real credentials.

I aim to acknowledge a report within 7 days and to publish a fix or a
mitigation before disclosing details.

## What counts as a vulnerability

- A credential-shaped value, or the source of a credential-looking file,
  written into a generated report.
- Reading or writing files outside the project and the configured output
  directory.
- Running project code or any other command in a situation the
  [trust model](https://github.com/msoleimani62/sarand#trust-model-scanning-runs-project-code)
  says sarand does not.
- A weakness in the release pipeline (tampered wheels, a leaked token).

## What does not

- Scanning a project runs that project's test suite (and, with `--quality`,
  `--security` or `--full`, its linters and audit tools). This is documented
  behaviour. Use `sarand --skip-tests` or an isolated machine for code you do
  not trust.
- Bugs in the third-party tools sarand launches (pytest, cargo, npm, gitleaks,
  and so on). Report those upstream.
- Secrets that sarand's best-effort detection does not recognise. That is a
  bug worth reporting as an ordinary issue; please describe the shape of the
  value, not the value.
