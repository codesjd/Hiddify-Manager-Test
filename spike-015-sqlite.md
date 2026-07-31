# SQLite Default Backend Spike Report (Phase 1)

## Full MySQL / Dialect-Specific SQL Grep Inventory

An audit of all raw SQL via `db.session.execute()`, `db.engine.execute()`, and `db_execute()` reveals the following MySQL-specific constructs:

### 1. `add_new_enum_values()` in `init_db.py` (Load-bearing at startup)
- **Files/Lines:** `hiddify-panel/src/hiddifypanel/panel/init_db.py` (1124, 1146)
- **SQL:** 
  - `SHOW COLUMNS FROM {table_name} LIKE :col;` (Line 1124)
  - `ALTER TABLE {table_name} MODIFY COLUMN \`{column_name}\` ENUM({enumstr});` (Line 1146)
- **Impact:** This function runs on every boot via `init_db()`, `restore()`, and `update()`. It dynamically synchronizes Python Enum values into MySQL ENUM columns. 
- **SQLite Compatibility:** SQLite does not support `SHOW COLUMNS LIKE` nor `ALTER TABLE ... MODIFY COLUMN ... ENUM()`. In fact, SQLite ignores ENUM constraints unless specifically configured with CHECK constraints.
- **Resolution:** This logic is fundamentally MySQL-specific and exists to workaround MySQL's strict ENUM typing. For SQLite, this step should be entirely skipped, or refactored using SQLAlchemy's Inspector (`sqlalchemy.inspect(db.engine).get_columns()`). The simplest fix is to conditionally early-return if `db.engine.dialect.name == 'sqlite'` since SQLite doesn't enforce ENUM values at the DB schema level anyway.

### 2. The `add_usage_json` Stored Procedure
- **Files/Lines:** `init_db.py` (427, 437, 465), `usage.py` (122)
- **SQL:** `CREATE PROCEDURE add_usage_json`, `JSON_TABLE`, `CALL add_usage_json`
- **Impact:** Uses MySQL JSON functions and stored procedures for batch usage updates.
- **Resolution:** Must be extracted into a backend-agnostic Python loop using SQLAlchemy for bulk updates (`db.session.execute(update(User)...)`).

### 3. Schema Alterations (Old Migrations in `init_db.py`)
- **Files/Lines:** `init_db.py` (569, 570, 680, 681, 1085, 1094, 1335, 1351, 1352)
- **SQL:** `ALTER TABLE ... MODIFY COLUMN ...`, `ALTER TABLE ... ADD COLUMN ...`
- **Impact:** These are hardcoded legacy schema migrations. SQLite does not support `MODIFY COLUMN`.
- **Resolution:** Guard these `ALTER` statements to execute only if `db.engine.dialect.name == 'mysql'`. New SQLite installs will create the schema fresh via `db.create_all()` and won't need these manual patches.

### 4. Standard ANSI SQL Operations (Compatible)
- **Files/Lines:** `child.py` (79), `admin.py` (216), `init_db.py` (1145, 1282), `xui.py` (17)
- **SQL:** `DELETE FROM ...`, `UPDATE ... SET ...`
- **Impact:** Standard raw queries.
- **Resolution:** Fully compatible with SQLite. No changes needed.

## Conclusion
The SQLite backend is viable. The only load-bearing logic tied to MySQL that must be addressed immediately for SQLite to boot and function is `add_new_enum_values()` and the `add_usage_json` procedure. Migrations can be dialect-guarded.
