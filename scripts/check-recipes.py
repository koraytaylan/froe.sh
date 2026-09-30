#!/usr/bin/env python3
"""Run every SQL recipe on the page against a small AEM-like export, in both dialects.

tests/fixture/tree.json is written out the way `froe export` would: Parquet
through the DuckDB CLI with froe's column names and types, and SQLite with the
schema froe creates (tests/fixture/sqlite-schema.sql). Each recipe's DuckDB and
SQLite forms must run and return the same rows.

Needs the `duckdb` CLI on PATH, or its path in $DUCKDB.
"""
import csv
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests/fixture"
DUCKDB = os.environ.get("DUCKDB") or shutil.which("duckdb")

NODE_COLUMNS = "{path:'VARCHAR',parent_path:'VARCHAR',name:'VARCHAR',depth:'INTEGER',primary_type:'VARCHAR'}"
PROPERTY_COLUMNS = (
    "{path:'VARCHAR',name:'VARCHAR',property_type:'VARCHAR',multiple:'BOOLEAN',position:'INTEGER',"
    "value:'VARCHAR',long_value:'BIGINT',double_value:'DOUBLE',boolean_value:'BOOLEAN',"
    "binary_length:'BIGINT',binary_reference:'VARCHAR'}"
)


def parent(path):
    return None if path == "/" else (path.rsplit("/", 1)[0] or "/")


def load_tree():
    tree = json.loads((FIXTURE / "tree.json").read_text())
    # Ancestors the fixture leaves out exist in a real export.
    for path in list(tree):
        while path != "/":
            path = parent(path)
            tree.setdefault(path, {"primary_type": "nt:unstructured", "properties": {}})
    return tree, sorted(tree, key=lambda p: [s for s in p.split("/") if s])


def property_rows(tree, paths):
    for path in paths:
        for name, prop in tree[path]["properties"].items():
            value = prop["value"]
            multiple = isinstance(value, list)
            for position, item in enumerate(value if multiple else [value]):
                row = dict(path=path, name=name, property_type=prop["type"], multiple=multiple,
                           position=position if multiple else None, value=None, long_value=None,
                           double_value=None, boolean_value=None, binary_length=None,
                           binary_reference=None)
                if prop["type"] == "Boolean":
                    row["boolean_value"] = item
                elif prop["type"] == "Long":
                    row["long_value"] = item
                elif prop["type"] == "Double":
                    row["double_value"] = item
                elif prop["type"] == "Binary":
                    # A number is an inline length; a string is an external blob reference.
                    row["binary_length" if isinstance(item, int) else "binary_reference"] = item
                else:
                    row["value"] = item
                yield row


def write_parquet(work, tree, paths, rows):
    nodes = work / "nodes.json"
    props = work / "properties.json"
    nodes.write_text("\n".join(json.dumps(dict(
        path=p, parent_path=parent(p), name="" if p == "/" else p.rsplit("/", 1)[1],
        depth=0 if p == "/" else p.count("/"), primary_type=tree[p]["primary_type"])) for p in paths))
    props.write_text("\n".join(json.dumps(r) for r in rows))
    (work / "export").mkdir()
    subprocess.run([DUCKDB, "-c", f"""
        COPY (SELECT * FROM read_json('{nodes}', format='newline_delimited', columns={NODE_COLUMNS}))
          TO '{work}/export/nodes.parquet' (FORMAT parquet);
        COPY (SELECT * FROM read_json('{props}', format='newline_delimited', columns={PROPERTY_COLUMNS}))
          TO '{work}/export/properties.parquet' (FORMAT parquet);
    """], check=True)


def write_sqlite(work, tree, paths, rows):
    db = sqlite3.connect(work / "export.db")
    db.executescript((FIXTURE / "sqlite-schema.sql").read_text())
    strings = {}

    def intern(text):
        if text is None:
            return None
        if text not in strings:
            strings[text] = len(strings) + 1
            db.execute("INSERT INTO strings VALUES (?, ?)", (strings[text], text))
        return strings[text]

    ids = {p: i + 1 for i, p in enumerate(paths)}
    db.execute("INSERT INTO export VALUES ('/')")
    for p in paths:
        db.execute("INSERT INTO nodes VALUES (?, ?, ?, ?, ?)", (
            ids[p], ids.get(parent(p)), intern("" if p == "/" else p.rsplit("/", 1)[1]),
            0 if p == "/" else p.count("/"), intern(tree[p]["primary_type"])))
    types = {}
    for r in rows:
        if r["property_type"] not in types:
            types[r["property_type"]] = len(types) + 1
            db.execute("INSERT INTO property_types VALUES (?, ?)", (types[r["property_type"]], r["property_type"]))
        db.execute("INSERT INTO properties VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            ids[r["path"]], intern(r["name"]), types[r["property_type"]], int(r["multiple"]),
            r["position"] or 0, intern(r["value"]), r["long_value"], r["double_value"],
            None if r["boolean_value"] is None else int(r["boolean_value"]),
            r["binary_length"], intern(r["binary_reference"])))
    db.commit()
    return db


def recipes():
    page = (ROOT / "public/index.html").read_text()

    def text(fragment):
        return html.unescape(re.sub(r"<[^>]+>", "", fragment))

    for m in re.finditer(r'<details class="recipe" id="([^"]+)".*?</details>', page, re.S):
        block = m.group(0)
        duck = text(re.search(r'data-dialect="duckdb"><code>(.*?)</code>', block, re.S).group(1))
        lite = text(re.search(r'data-dialect="sqlite"[^>]*><code>(.*?)</code>', block, re.S).group(1))
        yield (m.group(1),
               re.fullmatch(r'duckdb -c "(.*)"', duck, re.S).group(1),
               re.fullmatch(r'sqlite3 \./export\.db "(.*)"', lite, re.S).group(1))


def normalize(rows):
    """Rows as sorted text, so the dialects compare on content alone.

    SQLite has no boolean type, so true/false compare as 1/0. Rows are sorted
    because ties in ORDER BY have no defined order, and comma-joined cells are
    sorted because neither group_concat nor string_agg promises an order.
    """
    def cell(value):
        if value is None:
            return ""
        text = {"True": "1", "False": "0", "true": "1", "false": "0"}.get(str(value), str(value))
        return ",".join(sorted(text.split(","))) if "," in text else text

    return sorted(tuple(cell(v) for v in row) for row in rows)


def main():
    if not DUCKDB:
        sys.exit("check-recipes: the duckdb CLI is not on PATH; set $DUCKDB")
    tree, paths = load_tree()
    rows = list(property_rows(tree, paths))
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        write_parquet(work, tree, paths, rows)
        db = write_sqlite(work, tree, paths, rows)
        found = list(recipes())
        for rid, duck_sql, lite_sql in found:
            duck = subprocess.run([DUCKDB, "-csv", "-nullvalue", "", "-c", duck_sql], cwd=work, capture_output=True, text=True)
            problem = duck.stderr.strip() if duck.returncode else ""
            duck_rows = []
            if not problem:
                duck_rows = normalize(list(csv.reader(duck.stdout.splitlines()))[1:])
            try:
                lite_rows = normalize(db.execute(lite_sql).fetchall())
            except sqlite3.Error as error:
                problem = problem or f"sqlite: {error}"
                lite_rows = []
            if not problem and duck_rows != lite_rows:
                problem = f"dialects disagree\n    duckdb: {duck_rows}\n    sqlite: {lite_rows}"
            failures += bool(problem)
            print(f"{'FAIL' if problem else 'ok  '} {rid} ({len(duck_rows)} rows)" + (f"\n    {problem}" if problem else ""))
    print(f"{len(found) - failures}/{len(found)} recipes pass")
    sys.exit(1 if failures or not found else 0)


if __name__ == "__main__":
    main()
