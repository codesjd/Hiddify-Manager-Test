# Spike Report 027: Alembic Migrations

## 1. Current Schema State
- The canonical schema is defined by the SQLAlchemy models in `hiddifypanel.models` combined with the 141 iterative `_vNNN` functions in `init_db.py`.
- Because `db_execute` catches and swallows exceptions, production databases are potentially drifted (missing columns, indexes, or enum values that failed during a past upgrade, but `db_version` still advanced).
- This means we cannot simply run `alembic stamp head` on existing installs, because Alembic would assume they perfectly match the models, leaving the drift unfixed.

## 2. Cutover & Stamp Strategy
To safely transition existing, possibly drifted installs to Alembic without data loss, we must perform a **Reconciliation** before stamping.

### Strategy: Runtime Schema Comparison (`compare_metadata`)
1. **Define Baseline:** Create a single initial Alembic migration (`0001_baseline.py`) that creates the complete canonical schema from scratch.
2. **Fresh Installs:** Simply run `alembic upgrade head`. The baseline migration creates everything cleanly.
3. **Existing Installs (The Cutover):**
   - Detect existing installs (e.g., DB exists and has a `str_config` with `db_version`).
   - Use Alembic's `compare_metadata(context, target_metadata)` API internally at startup to diff the *actual* database schema against the *expected* SQLAlchemy models.
   - Execute the missing DDL (missing columns, tables, or index creations) programmatically based on the diff. This acts as a "heal" step for any past swallowed errors.
   - Once healed and perfectly matching the models, run `alembic stamp head` to mark the database as fully managed by Alembic.
   - Subsequent upgrades will use standard `alembic upgrade head`.

### Legacy `_vNNN` Migrations
- The 141 legacy steps in `init_db.py` are deprecated. 
- They can be deleted entirely since the healing script + `alembic stamp head` handles the reconciliation from any previous state.
- All new schema changes go into `migrations/versions/`.

## 3. Risks & Verification
- **SQLite vs MySQL Types:** The healing script must map SQLAlchemy types correctly depending on the active dialect (MySQL vs SQLite). Plan 015 (SQLite) will benefit greatly as Alembic handles dialect abstractions.
- **Verification:** Before merging Phase 2, take snapshots of real drifted databases (e.g., manually drop a column) and ensure the `compare_metadata` healing step successfully detects and applies the missing DDL without dropping data.
