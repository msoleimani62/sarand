# sarand-justfile-plugin

The smallest useful sarand plugin: it runs `just test` in projects that have
a `justfile`. Copy it as the starting point for your own plugin; the full
contract and author workflow are in [docs/PLUGINS.md](../../docs/PLUGINS.md).

Install it into the same environment as sarand:

```bash
pipx inject sarand ./examples/sarand-plugin-justfile
```
