# SQLite Default Backend Spike Report (Phase 1)

## Findings
Grep audit for MySQL dialect-specific SQL found instances primarily in `hiddify-panel/src/hiddifypanel/panel/init_db.py` and `hiddify-panel/src/hiddifypanel/panel/usage.py`.

### 1. The Stored Procedure (Load-bearing)
- **Files/Lines:** `init_db.py` (427, 437, 465), `usage.py` (122)
- **SQL:** `CREATE PROCEDURE add_usage_json`, `JSON_TABLE`, `CALL add_usage_json`
- **Issue:** Uses MySQL JSON functions and stored procedures for batch usage updates.
- **Resolution:** Must be extracted into a backend-agnostic Python loop using SQLAlchemy for bulk updates (`db.session.execute(update(User)...)`). This is the only significant logic move.

### 2. Schema Alterations (Migrations)
- **Files/Lines:** `init_db.py` (569, 570, 680, 681, 1085, 1094, 1146, 1335, 1351, 1352)
- **SQL:** `ALTER TABLE ... MODIFY COLUMN ...`, `ALTER TABLE ... ADD COLUMN ...`
- **Issue:** SQLite does not support `MODIFY COLUMN`. 
- **Resolution:** As per plan 027 (Alembic), these need to move to portable ORM/Core migrations. For now, we can conditionally execute these `ALTER` statements only if `db.engine.dialect.name == 'mysql'`, since new SQLite installs won't need past schema modifications (they create the schema fresh).

### 3. Schema Inspection
- **Files/Lines:** `init_db.py` (1124)
- **SQL:** `SHOW COLUMNS FROM ... LIKE ...`
- **Issue:** MySQL specific syntax.
- **Resolution:** Use SQLAlchemy `sqlalchemy.inspect(engine).get_columns(table_name)` instead.

### 4. Raw SQL Execution
- **Files/Lines:** `child.py` (79), `admin.py` (216), `init_db.py` (1145, 1282)
- **SQL:** `delete from ...`, `update child set id=0 ...`, `update admin_user set id=1 ...`
- **Issue:** Raw `db_execute` calls. 
- **Resolution:** Standard ANSI SQL (UPDATE/DELETE). Works fine on SQLite.

### Conclusion
The SQLite backend is viable. The only load-bearing logic tied to MySQL is the `add_usage_json` stored procedure. Schema migrations can be guarded or rewritten using SQLAlchemy's Inspector. No behavior changes are required outside of migrating usage aggregation to Python. Proceed to Phase 2.
