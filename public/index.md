# Froe

> The repository. Directly from disk. Froe is a Rust CLI and library for reading and maintaining Apache Jackrabbit Oak segment stores (segment-tar / TarMK), including those used by AEM.

Links: [Rust](https://www.rust-lang.org/) · [Apache Jackrabbit Oak](https://jackrabbit.apache.org/oak/) · [segment-tar / TarMK](https://jackrabbit.apache.org/oak/docs/nodestore/segment/overview.html) · [Adobe Experience Manager](https://experienceleague.adobe.com/en/docs/experience-manager)

Inspect, export, compare revisions and maintain offline. No running Oak instance. No JVM.

Rust ≥ 1.89 · Linux, macOS & Windows · [Apache-2.0](https://github.com/koraytaylan/froe/blob/develop/LICENSE) · [Source](https://github.com/koraytaylan/froe) · [docs.rs/froe](https://docs.rs/froe)

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
froe export /path/to/segmentstore --path /content \
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

- **Read — no repository writes, no lock.** Traverse nodes, inspect segments, diff revisions, trace history and export typed properties as [JSON lines](https://jsonlines.org/), [Parquet](https://parquet.apache.org/) or [SQLite](https://sqlite.org/).
- **Write — stopped repository, exclusive lock.** Compact, back up, restore, recover journals and manage checkpoints; mutating operations require confirmation.

<a id="download"></a>
## Download

Prebuilt binaries for every release are on [GitHub Releases](https://github.com/koraytaylan/froe/releases/latest); verify archives against the release's `SHA256SUMS`.

- Linux x86_64: `froe-<version>-x86_64-unknown-linux-musl.tar.gz` (static musl build)
- Linux ARM64: `froe-<version>-aarch64-unknown-linux-musl.tar.gz` (static musl build)
- macOS Apple silicon: `froe-<version>-aarch64-apple-darwin.tar.gz`
- Windows x86_64: `froe-<version>-x86_64-pc-windows-msvc.zip`

<a id="build"></a>
## Build from source

One binary. A library, too. The CLI includes Parquet and SQLite export support; the core crate exposes the repository traversal API. See the [quick start](https://github.com/koraytaylan/froe#quick-start).

```sh
git clone https://github.com/koraytaylan/froe.git
cd froe
cargo build --release
./target/release/froe --help
```

<a id="operations"></a>
## Repository operations

- **Audit a content snapshot.** Export nodes and typed properties, then query locally in [DuckDB](https://duckdb.org/) or SQLite; repeat Parquet exports decode changed subtrees. See the [SQL examples](#examples).
- **Recover a missing journal.** Use `check` to inspect consistency, then `recover-journal` to reconstruct the journal from surviving segments with Oak stopped. See the [recovery workflow](https://github.com/koraytaylan/froe/blob/develop/README.md).
- **Inspect and rebuild indexes.** Read index definitions and check their indexed state; dump [Lucene](https://lucene.apache.org/) data or import and reindex offline, subject to supported features. See the [index guide](https://github.com/koraytaylan/froe/blob/develop/docs/index.md) (import/reindex beta).

<a id="examples"></a>
## SQL over an AEM repository export

Export the whole tree once, then query the files; these 25 recipes read exported data and do not modify the repository.

```sh
# Choose the format for your SQL client
froe export /path/to/segmentstore --format parquet --output ./export
froe export /path/to/segmentstore --format sqlite --output ./export.db
```

- **JCR-SQL2 inside Oak: selects nodes, needs an index.** No `COUNT`, `GROUP BY`, `HAVING`, CTEs or window functions. A query no index covers traverses the repository on the running instance, and Oak stops it after 100,000 reads by default.
- **SQL over an export: any query, no index to plan for.** Aggregates, CTEs, window functions and joins in DuckDB or SQLite, against files on your machine. Every query scans or joins the export; none of them can slow down the instance.

Parquet stores one row per node and one row per property value; SQLite exposes `node_paths` and `properties_expanded`. Completed Parquet exports carry matching revision stamps, but a query during file replacement can observe a mixed pair; see the [export consistency contract](https://github.com/koraytaylan/froe/blob/develop/README.md#quick-start).

<a id="counts"></a>
### AEM page counts by site

Count cq:Page nodes under /content, grouped by the first path component beneath it.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT
    regexp_extract(path, '^(/content/[^/]+)', 1) AS site,
    count(*) AS pages,
    rank() OVER (ORDER BY count(*) DESC) AS rank
  FROM './export/nodes.parquet'
  WHERE primary_type = 'cq:Page'
    AND path LIKE '/content/%'
  GROUP BY 1
  ORDER BY pages DESC;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT
    substr(path, 1, 9 + instr(substr(path || '/', 10), '/') - 1) AS site,
    count(*) AS pages,
    rank() OVER (ORDER BY count(*) DESC) AS rank
  FROM node_paths
  WHERE primary_type = 'cq:Page'
    AND path LIKE '/content/%'
  GROUP BY 1
  ORDER BY pages DESC;"
```

<a id="component-pages"></a>
### AEM pages using a component

List pages whose content contains a component with the given sling:resourceType; replace mysite/components/teaser with yours.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT DISTINCT n.path AS page
  FROM './export/properties.parquet' p
  JOIN './export/nodes.parquet' n
    ON n.path = split_part(p.path, '/jcr:content/', 1)
  WHERE p.name = 'sling:resourceType'
    AND p.value = 'mysite/components/teaser'
    AND n.primary_type = 'cq:Page'
  ORDER BY 1;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT DISTINCT n.path AS page
  FROM properties_expanded p
  JOIN node_paths n
    ON n.path = substr(p.path, 1, instr(p.path, '/jcr:content/') - 1)
  WHERE p.name = 'sling:resourceType'
    AND p.value = 'mysite/components/teaser'
    AND n.primary_type = 'cq:Page'
  ORDER BY 1;"
```

<a id="template-pages"></a>
### AEM pages using a template

List pages whose jcr:content names the given cq:template; editable templates live under /conf, static ones under /apps.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT n.path AS page
  FROM './export/properties.parquet' p
  JOIN './export/nodes.parquet' n
    ON p.path = n.path || '/jcr:content'
  WHERE p.name = 'cq:template'
    AND p.value = '/conf/mysite/settings/wcm/templates/article-page'
    AND n.primary_type = 'cq:Page'
  ORDER BY 1;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT n.path AS page
  FROM properties_expanded p
  JOIN node_paths n
    ON p.path = n.path || '/jcr:content'
  WHERE p.name = 'cq:template'
    AND p.value = '/conf/mysite/settings/wcm/templates/article-page'
    AND n.primary_type = 'cq:Page'
  ORDER BY 1;"
```

<a id="template-usage"></a>
### AEM page counts by template

Count pages per cq:template; templates no page uses do not appear.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT p.value AS template, count(*) AS pages
  FROM './export/properties.parquet' p
  JOIN './export/nodes.parquet' n
    ON p.path = n.path || '/jcr:content'
  WHERE p.name = 'cq:template'
    AND n.primary_type = 'cq:Page'
  GROUP BY 1
  ORDER BY pages DESC, 1;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT p.value AS template, count(*) AS pages
  FROM properties_expanded p
  JOIN node_paths n
    ON p.path = n.path || '/jcr:content'
  WHERE p.name = 'cq:template'
    AND n.primary_type = 'cq:Page'
  GROUP BY 1
  ORDER BY pages DESC, 1;"
```

<a id="tagged-pages"></a>
### AEM pages with a tag

cq:tags is multivalued, so each tag is its own row; match the form your repository stores, a tag ID or a /content/cq:tags path.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT n.path AS page
  FROM './export/properties.parquet' p
  JOIN './export/nodes.parquet' n
    ON p.path = n.path || '/jcr:content'
  WHERE p.name = 'cq:tags'
    AND p.value = 'mysite:topics/news'
    AND n.primary_type = 'cq:Page'
  ORDER BY 1;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT n.path AS page
  FROM properties_expanded p
  JOIN node_paths n
    ON p.path = n.path || '/jcr:content'
  WHERE p.name = 'cq:tags'
    AND p.value = 'mysite:topics/news'
    AND n.primary_type = 'cq:Page'
  ORDER BY 1;"
```

<a id="asset-pages"></a>
### AEM pages referencing an asset

Find pages with a property whose value is exactly the asset path, such as fileReference; links inside rich text are not matched.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT DISTINCT n.path AS page, p.name AS property
  FROM './export/properties.parquet' p
  JOIN './export/nodes.parquet' n
    ON n.path = split_part(p.path || '/', '/jcr:content/', 1)
  WHERE p.value = '/content/dam/mysite/logo.svg'
    AND n.primary_type = 'cq:Page'
  ORDER BY 1, 2;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT DISTINCT n.path AS page, p.name AS property
  FROM properties_expanded p
  JOIN node_paths n
    ON n.path = substr(p.path, 1, instr(p.path || '/', '/jcr:content/') - 1)
  WHERE p.value = '/content/dam/mysite/logo.svg'
    AND n.primary_type = 'cq:Page'
  ORDER BY 1, 2;"
```

<a id="fragment-pages"></a>
### Experience fragments on AEM pages

Map each fragmentVariationPath placed in page content to its page; fragments in editable template structure live under /conf and are not listed.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT p.value AS fragment, n.path AS page
  FROM './export/properties.parquet' p
  JOIN './export/nodes.parquet' n
    ON n.path = split_part(p.path, '/jcr:content/', 1)
  WHERE p.name = 'fragmentVariationPath'
    AND n.primary_type = 'cq:Page'
  ORDER BY 1, 2;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT p.value AS fragment, n.path AS page
  FROM properties_expanded p
  JOIN node_paths n
    ON n.path = substr(p.path, 1, instr(p.path, '/jcr:content/') - 1)
  WHERE p.name = 'fragmentVariationPath'
    AND n.primary_type = 'cq:Page'
  ORDER BY 1, 2;"
```

<a id="stale-pages"></a>
### AEM pages not modified since a date

Compare cq:lastModified as a timestamp, so time zone offsets are honored; pages never edited have no cq:lastModified and are not listed.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT n.path AS page, p.value AS last_modified
  FROM './export/properties.parquet' p
  JOIN './export/nodes.parquet' n
    ON p.path = n.path || '/jcr:content'
  WHERE p.name = 'cq:lastModified'
    AND p.property_type = 'Date'
    AND n.primary_type = 'cq:Page'
    AND CAST(p.value AS TIMESTAMPTZ) < TIMESTAMPTZ '2025-01-01 00:00:00+00'
  ORDER BY CAST(p.value AS TIMESTAMPTZ);"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT n.path AS page, p.value AS last_modified
  FROM properties_expanded p
  JOIN node_paths n
    ON p.path = n.path || '/jcr:content'
  WHERE p.name = 'cq:lastModified'
    AND p.property_type = 'Date'
    AND n.primary_type = 'cq:Page'
    AND julianday(p.value) < julianday('2025-01-01')
  ORDER BY julianday(p.value);"
```

<a id="editors"></a>
### Last editors by page count

Group pages by cq:lastModifiedBy; only the most recent editor is recorded on the page, earlier ones live in version history.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT p.value AS editor, count(*) AS pages
  FROM './export/properties.parquet' p
  JOIN './export/nodes.parquet' n
    ON p.path = n.path || '/jcr:content'
  WHERE p.name = 'cq:lastModifiedBy'
    AND n.primary_type = 'cq:Page'
  GROUP BY 1
  ORDER BY pages DESC, 1;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT p.value AS editor, count(*) AS pages
  FROM properties_expanded p
  JOIN node_paths n
    ON p.path = n.path || '/jcr:content'
  WHERE p.name = 'cq:lastModifiedBy'
    AND n.primary_type = 'cq:Page'
  GROUP BY 1
  ORDER BY pages DESC, 1;"
```

<a id="missing-descriptions"></a>
### AEM pages without a description

Find site pages with no non-empty jcr:description, the page property most page components render as the meta description.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT n.path AS page
  FROM './export/nodes.parquet' n
  WHERE n.primary_type = 'cq:Page'
    AND n.path LIKE '/content/%'
    AND n.path NOT LIKE '/content/experience-fragments/%'
    AND NOT EXISTS (
      SELECT 1 FROM './export/properties.parquet' p
      WHERE p.path = n.path || '/jcr:content'
        AND p.name = 'jcr:description'
        AND p.value <> ''
    )
  ORDER BY 1;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT n.path AS page
  FROM node_paths n
  WHERE n.primary_type = 'cq:Page'
    AND n.path LIKE '/content/%'
    AND n.path NOT LIKE '/content/experience-fragments/%'
    AND NOT EXISTS (
      SELECT 1 FROM properties_expanded p
      WHERE p.path = n.path || '/jcr:content'
        AND p.name = 'jcr:description'
        AND p.value <> ''
    )
  ORDER BY 1;"
```

<a id="redirects"></a>
### AEM pages that redirect

List cq:redirectTarget values and whether the target is in the export; external URLs and partial exports report false.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT
    n.path AS page,
    p.value AS target,
    t.path IS NOT NULL AS target_in_export
  FROM './export/properties.parquet' p
  JOIN './export/nodes.parquet' n
    ON p.path = n.path || '/jcr:content'
  LEFT JOIN './export/nodes.parquet' t
    ON t.path = p.value
  WHERE p.name = 'cq:redirectTarget'
    AND n.primary_type = 'cq:Page'
  ORDER BY 1;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT
    n.path AS page,
    p.value AS target,
    t.path IS NOT NULL AS target_in_export
  FROM properties_expanded p
  JOIN node_paths n
    ON p.path = n.path || '/jcr:content'
  LEFT JOIN node_paths t
    ON t.path = p.value
  WHERE p.name = 'cq:redirectTarget'
    AND n.primary_type = 'cq:Page'
  ORDER BY 1;"
```

<a id="oak-indexes"></a>
### Oak index definitions

Inventory index type, async lane and reindex flag; froe index list provides the dedicated store-level view.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT
    n.path,
    max(CASE WHEN p.name = 'type' THEN p.value END) AS index_type,
    group_concat(DISTINCT CASE WHEN p.name = 'async' THEN p.value END) AS lane,
    max(CASE WHEN p.name = 'reindex' THEN p.value END) AS reindex
  FROM './export/nodes.parquet' n
  JOIN './export/properties.parquet' p
    ON p.path = n.path
  WHERE n.primary_type = 'oak:QueryIndexDefinition'
  GROUP BY 1
  ORDER BY 1;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT
    n.path,
    max(CASE WHEN p.name = 'type' THEN p.value END) AS index_type,
    group_concat(DISTINCT CASE WHEN p.name = 'async' THEN p.value END) AS lane,
    max(CASE WHEN p.name = 'reindex' THEN p.value END) AS reindex
  FROM node_paths n
  JOIN properties_expanded p
    ON p.path = n.path
  WHERE n.primary_type = 'oak:QueryIndexDefinition'
  GROUP BY 1
  ORDER BY 1;"
```

<a id="unused"></a>
### DAM assets without path references

Candidates with no external property value naming the asset or a descendant; UUID, embedded and external references are not covered, so this is not a deletion list.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT a.path
  FROM './export/nodes.parquet' a
  WHERE a.primary_type = 'dam:Asset'
    AND NOT EXISTS (
      SELECT 1 FROM './export/properties.parquet' p
      WHERE (p.value = a.path
        OR substr(p.value, 1, length(a.path) + 1) = a.path || '/')
        AND p.path <> a.path
        AND substr(p.path, 1, length(a.path) + 1) <> a.path || '/'
    )
  ORDER BY a.path;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT a.path
  FROM node_paths a
  WHERE a.primary_type = 'dam:Asset'
    AND NOT EXISTS (
      SELECT 1 FROM properties_expanded p
      WHERE (p.value = a.path
        OR substr(p.value, 1, length(a.path) + 1) = a.path || '/')
        AND p.path <> a.path
        AND substr(p.path, 1, length(a.path) + 1) <> a.path || '/'
    )
  ORDER BY a.path;"
```

<a id="asset-formats"></a>
### DAM assets by MIME type

Group assets by dc:format with the original renditions' sizes; external binaries have no recorded length, so they are counted separately.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT
    m.value AS mime_type,
    count(*) AS assets,
    sum(o.binary_length) AS inline_bytes,
    count(o.binary_reference) AS external
  FROM './export/properties.parquet' m
  JOIN './export/nodes.parquet' a
    ON m.path = a.path || '/jcr:content/metadata'
  LEFT JOIN './export/properties.parquet' o
    ON o.path = a.path || '/jcr:content/renditions/original/jcr:content'
    AND o.name = 'jcr:data'
  WHERE m.name = 'dc:format'
    AND a.primary_type = 'dam:Asset'
  GROUP BY 1
  ORDER BY assets DESC, 1;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT
    m.value AS mime_type,
    count(*) AS assets,
    sum(o.binary_length) AS inline_bytes,
    count(o.binary_reference) AS external
  FROM properties_expanded m
  JOIN node_paths a
    ON m.path = a.path || '/jcr:content/metadata'
  LEFT JOIN properties_expanded o
    ON o.path = a.path || '/jcr:content/renditions/original/jcr:content'
    AND o.name = 'jcr:data'
  WHERE m.name = 'dc:format'
    AND a.primary_type = 'dam:Asset'
  GROUP BY 1
  ORDER BY assets DESC, 1;"
```

<a id="fragment-models"></a>
### Content fragments by model

Count content fragments per cq:model, read from each fragment's jcr:content/data node.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT p.value AS model, count(*) AS fragments
  FROM './export/properties.parquet' p
  JOIN './export/nodes.parquet' a
    ON p.path = a.path || '/jcr:content/data'
  WHERE p.name = 'cq:model'
    AND a.primary_type = 'dam:Asset'
  GROUP BY 1
  ORDER BY fragments DESC, 1;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT p.value AS model, count(*) AS fragments
  FROM properties_expanded p
  JOIN node_paths a
    ON p.path = a.path || '/jcr:content/data'
  WHERE p.name = 'cq:model'
    AND a.primary_type = 'dam:Asset'
  GROUP BY 1
  ORDER BY fragments DESC, 1;"
```

<a id="types-per-site"></a>
### Sling resource types by site

Rank sling:resourceType usage within each site; ties can return more than five types.

DuckDB over Parquet:

```sh
duckdb -c "
  WITH uses AS (
    SELECT
      regexp_extract(path, '^(/content/[^/]+)', 1) AS site,
      value AS resource_type,
      count(DISTINCT path) AS uses
    FROM './export/properties.parquet'
    WHERE name = 'sling:resourceType'
      AND path LIKE '/content/%'
    GROUP BY 1, 2
  )
  SELECT site, resource_type, uses, rank
  FROM (
    SELECT
      site,
      resource_type,
      uses,
      rank() OVER (PARTITION BY site ORDER BY uses DESC) AS rank
    FROM uses
  )
  WHERE rank <= 5
  ORDER BY site, rank;"
```

SQLite:

```sh
sqlite3 ./export.db "
  WITH uses AS (
    SELECT
      substr(path, 1, 9 + instr(substr(path || '/', 10), '/') - 1) AS site,
      value AS resource_type,
      count(DISTINCT path) AS uses
    FROM properties_expanded
    WHERE name = 'sling:resourceType'
      AND path LIKE '/content/%'
    GROUP BY 1, 2
  )
  SELECT site, resource_type, uses, rank
  FROM (
    SELECT
      site,
      resource_type,
      uses,
      rank() OVER (PARTITION BY site ORDER BY uses DESC) AS rank
    FROM uses
  )
  WHERE rank <= 5
  ORDER BY site, rank;"
```

<a id="duplicate-titles"></a>
### Duplicate content titles

Find repeated jcr:title values across distinct nodes; repeated titles are not necessarily errors.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT value AS title, count(DISTINCT path) AS uses
  FROM './export/properties.parquet'
  WHERE name = 'jcr:title'
    AND value IS NOT NULL
  GROUP BY 1
  HAVING count(DISTINCT path) > 1
  ORDER BY uses DESC;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT value AS title, count(DISTINCT path) AS uses
  FROM properties_expanded
  WHERE name = 'jcr:title'
    AND value IS NOT NULL
  GROUP BY 1
  HAVING count(DISTINCT path) > 1
  ORDER BY uses DESC;"
```

<a id="crowded-folders"></a>
### Folders with many direct children

Find parents with more than 200 immediate children; this is a structural inventory, not a performance diagnosis.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT parent_path, count(*) AS children
  FROM './export/nodes.parquet'
  WHERE parent_path IS NOT NULL
  GROUP BY 1
  HAVING count(*) > 200
  ORDER BY children DESC;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT p.path AS parent_path, count(*) AS children
  FROM nodes c
  JOIN node_paths p ON p.id = c.parent_id
  GROUP BY p.id, p.path
  HAVING count(*) > 200
  ORDER BY children DESC;"
```

<a id="one-off-types"></a>
### Resource types used once

Find sling:resourceType values used by a single node; each result needs review before changing content.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT value AS resource_type, count(DISTINCT path) AS uses
  FROM './export/properties.parquet'
  WHERE name = 'sling:resourceType'
  GROUP BY 1
  HAVING count(DISTINCT path) = 1
  ORDER BY 1;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT value AS resource_type, count(DISTINCT path) AS uses
  FROM properties_expanded
  WHERE name = 'sling:resourceType'
  GROUP BY 1
  HAVING count(DISTINCT path) = 1
  ORDER BY 1;"
```

<a id="hot-refs"></a>
### Widely reused DAM assets

Count distinct nodes with fileReference values pointing into /content/dam; this covers that property only.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT value AS asset, count(DISTINCT path) AS refs
  FROM './export/properties.parquet'
  WHERE name = 'fileReference'
    AND value LIKE '/content/dam/%'
  GROUP BY 1
  HAVING count(DISTINCT path) >= 10
  ORDER BY refs DESC;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT value AS asset, count(DISTINCT path) AS refs
  FROM properties_expanded
  WHERE name = 'fileReference'
    AND value LIKE '/content/dam/%'
  GROUP BY 1
  HAVING count(DISTINCT path) >= 10
  ORDER BY refs DESC;"
```

<a id="fat-nodes"></a>
### Nodes with many properties

Count distinct property names, not property values; multivalued properties contribute one name.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT path, count(DISTINCT name) AS props
  FROM './export/properties.parquet'
  GROUP BY 1
  HAVING count(DISTINCT name) > 80
  ORDER BY props DESC
  LIMIT 50;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT path, count(DISTINCT name) AS props
  FROM properties_expanded
  GROUP BY 1
  HAVING count(DISTINCT name) > 80
  ORDER BY props DESC
  LIMIT 50;"
```

<a id="dangling"></a>
### Paths absent from the export

Review absolute path-shaped values with no exported node; a partial export or a string that is not a repository reference can produce a match.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT p.path, p.name, p.value
  FROM './export/properties.parquet' p
  WHERE p.value LIKE '/%'
    AND NOT EXISTS (
      SELECT 1 FROM './export/nodes.parquet' n
      WHERE n.path = p.value
    );"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT p.path, p.name, p.value
  FROM properties_expanded p
  WHERE p.value LIKE '/%'
    AND NOT EXISTS (
      SELECT 1 FROM node_paths n
      WHERE n.path = p.value
    );"
```

<a id="broken-pages"></a>
### AEM pages without jcr:content

Find cq:Page nodes whose jcr:content child is absent; use a full-depth export before treating a result as missing content.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT n.path
  FROM './export/nodes.parquet' n
  WHERE n.primary_type = 'cq:Page'
    AND NOT EXISTS (
      SELECT 1 FROM './export/nodes.parquet' c
      WHERE c.path = n.path || '/jcr:content'
    )
  ORDER BY 1;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT n.path
  FROM node_paths n
  WHERE n.primary_type = 'cq:Page'
    AND NOT EXISTS (
      SELECT 1 FROM node_paths c
      WHERE c.path = n.path || '/jcr:content'
    )
  ORDER BY 1;"
```

<a id="replication"></a>
### Recorded replication actions

Group cq:lastReplicationAction values by distinct node; historical metadata does not establish current publish state.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT value AS action, count(DISTINCT path) AS nodes
  FROM './export/properties.parquet'
  WHERE name = 'cq:lastReplicationAction'
  GROUP BY 1
  ORDER BY 2 DESC;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT value AS action, count(DISTINCT path) AS nodes
  FROM properties_expanded
  WHERE name = 'cq:lastReplicationAction'
  GROUP BY 1
  ORDER BY 2 DESC;"
```

<a id="binaries"></a>
### Largest stored binaries

Rank non-null binary_length values; external binaries are represented by binary_reference rather than inline bytes.

DuckDB over Parquet:

```sh
duckdb -c "
  SELECT path, name, binary_length
  FROM './export/properties.parquet'
  WHERE binary_length IS NOT NULL
  ORDER BY binary_length DESC
  LIMIT 25;"
```

SQLite:

```sh
sqlite3 ./export.db "
  SELECT path, name, binary_length
  FROM properties_expanded
  WHERE binary_length IS NOT NULL
  ORDER BY binary_length DESC
  LIMIT 25;"
```

<a id="reference"></a>
## Implementation & reference

Source is the specification.

- Reads `store.version` 1 and 2; maintenance targets version 2, with conditional upgrades for version 1 cleanup.
- Write-path interoperability is tested with Oak 1.90.0 in [Apache Sling](https://sling.apache.org/); AEM itself and external blob stores remain unverified. See the [interoperability test contract](https://github.com/koraytaylan/froe/blob/develop/docs/interop.md).
- Lucene index import and reindex are beta in v0.12.0; unsupported rebuild features are refused rather than approximated.

- [Storage format](https://github.com/koraytaylan/froe/blob/develop/docs/storage-format.md): archives, segments and record encodings.
- [Offline maintenance](https://github.com/koraytaylan/froe/blob/develop/docs/compact.md): planning, retention and failure behavior.
- [Index operations](https://github.com/koraytaylan/froe/blob/develop/docs/index.md): definitions, consistency, transport and rebuilds.
- [Oak feature map](https://github.com/koraytaylan/froe/blob/develop/docs/oak-segment-tar-feature-map.md): implemented, planned and out of scope.
