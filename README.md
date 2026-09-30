# froe.sh

The website for [Froe](https://github.com/koraytaylan/froe), a Rust CLI and library for reading and maintaining Apache Jackrabbit Oak segment stores. Live at <https://froe.sh>.

## Layout

| Path | What it is |
| --- | --- |
| `public/index.html` | The page: one self-contained HTML file, styles and scripts inline. |
| `public/index.md` | The page in markdown, generated from `index.html` by `scripts/index-md.py`. |
| `public/llms.txt`, `robots.txt`, `sitemap.xml` | Crawler and LLM entry points. |
| `public/og.jpg`, `favicon.*`, `apple-touch-icon.png` | Share card and icons; `og.jpg` is a 1200×630 headless Chrome screenshot of `scripts/og.html`. |
| `scripts/check-recipes.py`, `tests/fixture/` | Runs every SQL recipe on the page against a small AEM-like export, in DuckDB and SQLite. |
| `src/worker.js` | Cloudflare Worker in front of the static files; sends `http://` and `www.froe.sh` to `https://froe.sh` with a 301. |
| `wrangler.jsonc` | Worker name, static assets and the `froe.sh` / `www.froe.sh` custom domains. |

The download links point at the v0.12.0 release in the HTML; when the page loads it swaps in the newest [GitHub release](https://github.com/koraytaylan/froe/releases/latest).

## Editing

Edit `public/index.html`, then regenerate the markdown copy:

```sh
python3 scripts/index-md.py
```

After touching a recipe, check that both dialects still run and agree (needs the [DuckDB CLI](https://duckdb.org/docs/installation/) on `PATH`, or its path in `$DUCKDB`):

```sh
python3 scripts/check-recipes.py
```

The fixture is `tests/fixture/tree.json`; `tests/fixture/sqlite-schema.sql` is the schema `froe export` creates, copied from the froe repository.

Preview locally with Wrangler:

```sh
npx wrangler@4 dev
```

## Deploying

Every push to `main` runs `.github/workflows/cloudflare.yml`: it checks the recipes, then regenerates `index.md` and runs `wrangler deploy`. A failing recipe stops the deploy. It can also be run by hand from the Actions tab.

The workflow needs two repository secrets:

- `CLOUDFLARE_API_TOKEN`: the `froe-deploy` token, limited to the `froe` Worker and routes on the `froe.sh` zone.
- `CLOUDFLARE_ACCOUNT_ID`: the Cloudflare account that owns the Worker.
