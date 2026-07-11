# SQLite Default Backend Spike Report (Phase 1)

## Findings
Grep audit for MySQL dialect-specific SQL found 24 instances (12 unique sites, as `init_db.py` was checked twice in the glob match) primarily in `hiddify-panel/src/hiddifypanel/panel/init_db.py`.

### 1. The Stored Procedure (Load-bearing)
- **Lines:** 427, 437
- **SQL:** `CREATE PROCEDURE add_usage_json`, `JSON_TABLE`
- **Issue:** Uses MySQL JSON functions and stored procedures. 
- **Resolution:** Must be rewritten as backend-agnostic Python code using SQLAlchemy bulk updates. This is the only significant logic move needed.

### 2. Schema Alterations (Migrations)
- **Lines:** 569, 570, 680, 681, 1094, 1146, 1335, 1351, 1352
- **SQL:** `ALTER TABLE ... MODIFY COLUMN ...`
- **Issue:** SQLite does not support `MODIFY COLUMN`. 
- **Resolution:** These schema migrations need to be rewritten. In SQLite, column modifications usually require table recreation or using Alembic's batch mode (`with op.batch_alter_table(...) as batch_op:`), though for raw SQLAlchemy core, we'd need table recreation. However, since the plan notes Phase 2 will port these to portable SQLAlchemy ORM/Core and plan 027 introduces Alembic, the migration strategy is clear. 

### 3. Schema Inspection
- **Lines:** 1124
- **SQL:** `SHOW COLUMNS FROM ...`
- **Issue:** MySQL specific. 
- **Resolution:** Can be replaced with SQLAlchemy's Inspector (`sqlalchemy.inspect(engine).get_columns(table_name)`).

### Conclusion
The SQLite backend is viable. The only load-bearing hot path requiring logic extraction is the `add_usage_json` stored procedure, which is already scoped in Phase 2. The remaining issues are entirely schema migration syntax (`MODIFY COLUMN`, `SHOW COLUMNS`) which can be handled via SQLAlchemy's abstraction or batch operations. No behavior changes are required outside of migrating the usage aggregation to Python. Proceed to Phase 2.
