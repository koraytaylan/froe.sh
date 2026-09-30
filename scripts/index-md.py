#!/usr/bin/env python3
"""Write public/index.md from public/index.html so the markdown never drifts from the page."""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "public/index.html").read_text()


def text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def code(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).rstrip()


def recipes():
    out = []
    for m in re.finditer(r'<details class="recipe" id="([^"]+)".*?</details>', PAGE, re.S):
        block = m.group(0)
        title = text(re.search(r"<summary><span>(.*?)</span>", block).group(1))
        note = text(re.search(r'<div class="recipe-note"><p>(.*?)</p>', block, re.S).group(1))
        duck = code(re.search(r'<pre data-dialect="duckdb"><code>(.*?)</code></pre>', block, re.S).group(1))
        lite = code(re.search(r'<pre data-dialect="sqlite"[^>]*><code>(.*?)</code></pre>', block, re.S).group(1))
        out.append(
            f'<a id="{m.group(1)}"></a>\n### {title}\n\n{note}\n\n'
            f"DuckDB over Parquet:\n\n```sh\n{duck}\n```\n\nSQLite:\n\n```sh\n{lite}\n```\n"
        )
    return out


R = recipes()
GH = "https://github.com/koraytaylan/froe"
DOC = f"{GH}/blob/develop"

md = f"""# Froe

> The repository. Directly from disk. Froe is a Rust CLI and library for reading and maintaining Apache Jackrabbit Oak segment stores (segment-tar / TarMK), including those used by AEM.

Inspect, export, compare revisions and maintain offline. No running Oak instance. No JVM.

Rust ≥ 1.89 · Linux & macOS · [Apache-2.0]({DOC}/LICENSE) · [Source]({GH}) · [docs.rs/froe](https://docs.rs/froe)

<a id="commands"></a>
## Working with a store

Inspect (read-only, live or stopped repository):

```sh
# Inspect the store and traverse content
froe summary /path/to/segmentstore
froe tree /path/to/segmentstore /content --depth 2

# Find consistent revisions
froe check /path/to/segmentstore
```

Export (read-only, typed content, analytical SQL):

```sh
# Export the content subtree to Parquet
froe export /path/to/segmentstore --path /content \\
  --format parquet --output ./export

# Query the exported nodes
duckdb -c "SELECT primary_type, count(*) AS nodes
  FROM './export/nodes.parquet'
  GROUP BY primary_type ORDER BY nodes DESC;"
```

Maintain (stopped repository, dry-run writes nothing):

```sh
# Preview the complete maintenance plan
froe compact /path/to/segmentstore --dry-run

# Apply with interactive confirmation
froe compact /path/to/segmentstore

# Full compaction purges orphaned version histories;
# --skip-purging-orphaned-version-histories keeps them.
```

Indexes (read-only, definitions and indexed-state checks):

```sh
# Inspect index definitions and async lanes
froe index list /path/to/segmentstore

# Check indexes against their indexed state
froe index check /path/to/segmentstore

# Offline index import and reindex: beta in v0.12.0
# See the index guide for supported definitions.
```

- **Read — no repository writes, no lock.** Traverse nodes, inspect segments, diff revisions, trace history and export typed properties as JSON lines, Parquet or SQLite.
- **Write — stopped repository, exclusive lock.** Compact, back up, restore, recover journals and manage checkpoints; mutating operations require confirmation.

<a id="download"></a>
## Download

Prebuilt binaries for every release are on [GitHub Releases]({GH}/releases/latest); verify archives against the release's `SHA256SUMS`.

- Linux x86_64: `froe-<version>-x86_64-unknown-linux-musl.tar.gz` (static musl build)
- Linux ARM64: `froe-<version>-aarch64-unknown-linux-musl.tar.gz` (static musl build)
- macOS Apple silicon: `froe-<version>-aarch64-apple-darwin.tar.gz`
- Windows x86_64: `froe-<version>-x86_64-pc-windows-msvc.zip`

<a id="build"></a>
## Build from source

One binary. A library, too. The CLI includes Parquet and SQLite export support; the core crate exposes the repository traversal API. See the [quick start]({GH}#quick-start).

```sh
git clone https://github.com/koraytaylan/froe.git
cd froe
cargo build --release
./target/release/froe --help
```

<a id="operations"></a>
## Repository operations

- **Audit a content snapshot.** Export nodes and typed properties, then query locally in DuckDB or SQLite; repeat Parquet exports decode changed subtrees. See the [SQL examples](#examples).
- **Recover a missing journal.** Use `check` to inspect consistency, then `recover-journal` to reconstruct the journal from surviving segments with Oak stopped. See the [recovery workflow]({DOC}/README.md).
- **Inspect and rebuild indexes.** Read index definitions and check their indexed state; dump Lucene data or import and reindex offline, subject to supported features. See the [index guide]({DOC}/docs/index.md) (import/reindex beta).

<a id="examples"></a>
## SQL over an AEM repository export

Export the whole tree once, then query the files; these {len(R)} recipes read exported data and do not modify the repository.

```sh
# Choose the format for your SQL client
froe export /path/to/segmentstore --format parquet --output ./export
froe export /path/to/segmentstore --format sqlite --output ./export.db
```

Parquet stores one row per node and one row per property value; SQLite exposes `node_paths` and `properties_expanded`. Completed Parquet exports carry matching revision stamps, but a query during file replacement can observe a mixed pair; see the [export consistency contract]({DOC}/README.md#quick-start).

""" + "\n".join(R) + f"""
<a id="reference"></a>
## Implementation & reference

Source is the specification.

- Reads `store.version` 1 and 2; maintenance targets version 2, with conditional upgrades for version 1 cleanup.
- Write-path interoperability is tested with Oak 1.90.0 in Apache Sling; AEM itself and external blob stores remain unverified. See the [interoperability test contract]({DOC}/docs/interop.md).
- Lucene index import and reindex are beta in v0.12.0; unsupported rebuild features are refused rather than approximated.

- [Storage format]({DOC}/docs/storage-format.md): archives, segments and record encodings.
- [Offline maintenance]({DOC}/docs/compact.md): planning, retention and failure behavior.
- [Index operations]({DOC}/docs/index.md): definitions, consistency, transport and rebuilds.
- [Oak feature map]({DOC}/docs/oak-segment-tar-feature-map.md): implemented, planned and out of scope.
"""

(ROOT / "public/index.md").write_text(md)
