# Kubernetes checks

sarand finds Helm charts, Kustomize overlays and raw manifests (see the report's
Kubernetes section). With `--quality` it runs, per chart and per overlay:

| Check | Tool | Needs |
|---|---|---|
| `helm lint <chart>` | `helm` | the chart's dependencies vendored in `charts/` |
| `kustomize build <overlay>` | `kustomize` | no remote base, no `helmCharts` generator |
| `kubeconform <chart or overlay>` | `helm` or `kustomize`, and `kubeconform` | opt-in, see below |

sarand never applies anything to a cluster. A check that cannot give a true
answer here is reported as skipped with the reason, never as a failure.

## Schema validation (opt-in)

Validating rendered manifests against the Kubernetes schemas is off by default,
for two reasons that are part of the design: `kubeconform` normally downloads
its schemas from the network, and sarand does not run checks that need the
network; and a rendered `Secret` must never end up in a report.

It turns on when the environment variable `SARAND_KUBECONFORM_SCHEMAS` names a
**local** directory of schemas:

```sh
git clone --depth 1 https://github.com/yannh/kubernetes-json-schema ~/k8s-schemas
export SARAND_KUBECONFORM_SCHEMAS=~/k8s-schemas
sarand --quality
```

What then happens, per chart: `helm template --output-dir` renders it into a
temporary directory, `kubeconform` checks that directory against the local
schemas only (`-strict -ignore-missing-schemas`), and the directory is deleted.
Per overlay the output of `kustomize build` is checked the same way. Only the
tool's error lines reach the report; the rendered manifests do not.

The directory must follow the layout of the `kubernetes-json-schema` project:
`<dir>/<version>-standalone-strict/<kind>-<group>-<version>.json`. The version
is `master` unless `SARAND_KUBECONFORM_VERSION` is set (for example `1.30.0`).

Things to know:

- A resource kind with no schema in the directory (a custom resource, for
  example) is skipped by `-ignore-missing-schemas`. If **no** resource of a chart
  has a schema, the check is reported as skipped with that reason instead of
  passing, so a wrong directory cannot look like a clean result.
- The check only covers charts and overlays, not loose manifest files.
- The path must not contain a brace (`{` or `}`); it becomes part of the
  `kubeconform` schema template.
