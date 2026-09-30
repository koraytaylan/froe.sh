-- The SQLite schema froe export writes, copied from
-- https://github.com/koraytaylan/froe/blob/develop/crates/froe-export/src/sqlite/schema.rs
-- Refresh it when that file changes.
CREATE TABLE strings(
    id INTEGER PRIMARY KEY,
    value TEXT NOT NULL UNIQUE
);
CREATE TABLE nodes(
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES nodes(id),
    name_id INTEGER NOT NULL REFERENCES strings(id),
    depth INTEGER NOT NULL,
    primary_type_id INTEGER REFERENCES strings(id)
);
CREATE TABLE property_types(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE properties(
    node_id INTEGER NOT NULL REFERENCES nodes(id),
    name_id INTEGER NOT NULL REFERENCES strings(id),
    type_id INTEGER NOT NULL REFERENCES property_types(id),
    multiple INTEGER NOT NULL CHECK (multiple IN (0, 1)),
    position INTEGER NOT NULL,
    value_id INTEGER REFERENCES strings(id),
    long_value INTEGER,
    double_value REAL,
    boolean_value INTEGER CHECK (boolean_value IN (0, 1)),
    binary_length INTEGER,
    binary_reference_id INTEGER REFERENCES strings(id),
    PRIMARY KEY (node_id, name_id, position)
) WITHOUT ROWID;
CREATE TABLE export(
    root_path TEXT NOT NULL
);
CREATE VIEW node_paths(id, path, depth, primary_type) AS
WITH RECURSIVE walk(id, path, depth, primary_type) AS (
    SELECT n.id, (SELECT root_path FROM export), 0, p.value
      FROM nodes n
      LEFT JOIN strings p ON p.id = n.primary_type_id
     WHERE n.parent_id IS NULL
    UNION ALL
    SELECT n.id,
           walk.path || CASE WHEN walk.path = '/' THEN '' ELSE '/' END || s.value,
           n.depth, p.value
      FROM nodes n
      JOIN walk ON n.parent_id = walk.id
      JOIN strings s ON s.id = n.name_id
      LEFT JOIN strings p ON p.id = n.primary_type_id
)
SELECT id, path, depth, primary_type FROM walk;
CREATE VIEW properties_expanded AS
SELECT np.path, sn.value AS name, pt.name AS property_type,
       p.multiple, p.position, sv.value AS value,
       p.long_value, p.double_value, p.boolean_value,
       p.binary_length, sr.value AS binary_reference
  FROM properties p
  JOIN node_paths np ON np.id = p.node_id
  JOIN strings sn ON sn.id = p.name_id
  JOIN property_types pt ON pt.id = p.type_id
  LEFT JOIN strings sv ON sv.id = p.value_id
  LEFT JOIN strings sr ON sr.id = p.binary_reference_id;
