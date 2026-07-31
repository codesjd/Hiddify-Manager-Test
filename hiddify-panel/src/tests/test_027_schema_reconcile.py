import os
os.environ['STDOUT_LOG_LEVEL'] = 'INFO'
os.environ['REDIS_URI_MAIN'] = 'redis://127.0.0.1:6379'
os.environ['REDIS_URI_SSE'] = 'redis://127.0.0.1:6379'
os.environ['HIDDIFY_CONFIG_PATH'] = '/opt/hiddify-manager'
from unittest.mock import patch
from sqlalchemy import text as sa_text

# `app` and `db_path` fixtures live in tests/conftest.py, shared across the
# whole suite (see that file's docstring for why: create_app() can only be
# called once per process). db_path is real/file-backed there specifically
# so reconcile_schema()'s pre-DDL backup (which shells out to the real
# `sqlite3` CLI and no-ops on ':memory:') can be exercised for real. Each
# test below is responsible for restoring the schema to a clean state
# before it finishes, so tests stay order-independent despite sharing one
# app/db for the whole session.


def _backup_path(db_path):
    return db_path.with_suffix(db_path.suffix + '.bak')


def _columns(db):
    with db.engine.connect() as conn:
        return [r[1] for r in conn.execute(sa_text("PRAGMA table_info(domain)"))]


def test_reconcile_heals_additive_drift(app, db_path):
    """Invariant 1: a genuinely missing column (simulating a past swallowed
    migration failure) gets created back, and the pre-DDL backup actually
    runs (proven by the .bak file landing on disk). Also leaves the schema
    clean again, since the heal itself restores the dropped column."""
    from hiddifypanel.database import db, reconcile_schema

    assert reconcile_schema() is True  # clean schema: nothing to heal

    with db.engine.connect() as conn:
        conn.execute(sa_text('ALTER TABLE domain DROP COLUMN alias'))
        conn.commit()
    assert 'alias' not in _columns(db), "test setup didn't actually drop the column"

    backup_path = _backup_path(db_path)
    if backup_path.exists():
        backup_path.unlink()  # prove *this* reconcile run creates it, not a stale one

    result = reconcile_schema()
    assert result is True, "additive drift (a missing column) should heal, not be flagged ambiguous"
    assert 'alias' in _columns(db), "reconcile_schema() did not actually re-add the missing column"
    assert backup_path.exists(), "additive heal ran DDL without the required pre-DDL backup existing on disk"


def test_reconcile_flags_ambiguous_diff_and_does_not_stamp(app):
    """Invariant 2: a diff that isn't a clean additive create (here: an
    extra column the models don't know about - the same shape a botched
    rename leaves behind, per the plan's own worked example) must be
    flagged as an error and NOT auto-resolved - specifically, the extra
    column must survive untouched, proving reconcile_schema() didn't
    guess and silently drop it."""
    from hiddifypanel.database import db, reconcile_schema

    with db.engine.connect() as conn:
        conn.execute(sa_text("ALTER TABLE domain ADD COLUMN legacy_unexpected_column VARCHAR(50)"))
        conn.commit()

    try:
        result = reconcile_schema()
        assert result is False, "an ambiguous (non-additive) diff must not report success"
        assert 'legacy_unexpected_column' in _columns(db), (
            "reconcile_schema() must never silently drop a column it can't explain - "
            "this is exactly the failure mode that would destroy data on a real rename"
        )
    finally:
        # Restore a clean schema for whichever test runs next, regardless
        # of file order.
        with db.engine.connect() as conn:
            conn.execute(sa_text("ALTER TABLE domain DROP COLUMN legacy_unexpected_column"))
            conn.commit()


def test_reconcile_aborts_all_ddl_if_backup_fails(app):
    """Invariant 3: if the pre-DDL backup can't be taken, reconcile_schema()
    must abort before running ANY DDL - not partially apply changes with
    no safety net. Simulated by making backup_db() fail; the previously-
    dropped column must still be missing afterward, proving no DDL ran.
    Then heals for real, so the shared schema is clean for any later run."""
    from hiddifypanel.database import db, reconcile_schema

    with db.engine.connect() as conn:
        conn.execute(sa_text('ALTER TABLE domain DROP COLUMN alias'))
        conn.commit()

    with patch('hiddifypanel.database.backup_db', return_value=False):
        result = reconcile_schema()

    assert result is False, "reconcile_schema() must fail when the backup fails, not proceed anyway"
    assert 'alias' not in _columns(db), (
        "DDL ran despite the backup failing - the mandatory pre-DDL backup invariant is not being enforced"
    )

    assert reconcile_schema() is True, "cleanup heal (real backup this time) should succeed"
    assert 'alias' in _columns(db), "cleanup heal did not actually restore the column"
