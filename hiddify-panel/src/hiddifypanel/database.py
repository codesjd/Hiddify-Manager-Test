from typing import Optional
from sqlalchemy.orm import  sessionmaker
from sqlalchemy.orm import as_declarative, declared_attr,relationship
import sqlalchemy.orm as sa_orm

# from sqlalchemy_utils import UUIDType
import re
import os
from sqlalchemy import Row, create_engine, text, Sequence
import sqlalchemy as sa


# class SQLAlchemy:
    
#     def __init__(self):
#         self.engine = create_engine(os.environ.get("SQLALCHEMY_DATABASE_URI"))
#         self.session_maker = sessionmaker(bind=self.engine)
#         self.session=self.session_maker()
#         @as_declarative()
#         class Base:
#             @declared_attr
#             def __tablename__(cls):
#                 return cls.__name__.lower()

#             @classmethod
#             @property
#             def query(cls):
#                 return self.session.query(cls)
            
    
#         self.Query=sa_orm.Query
#         self.Model=Base
#         self.Table=sa.Table
#         self.Column=sa.Column
#         self.Integer=sa.Integer
#         self.ForeignKey=sa.ForeignKey

    # def _set_rel_query(self, kwargs) -> None:
    #         """Apply the extension's :attr:`Query` class as the default for relationships
    #         and backrefs.

    #         :meta private:
    #         """
    #         kwargs.setdefault("query_class", self.Query)

    #         if "backref" in kwargs:
    #             backref = kwargs["backref"]

    #             if isinstance(backref, str):
    #                 backref = (backref, {})

    #             backref[1].setdefault("query_class", self.Query)

        
    # def relationship(
    #         self, *args, **kwargs
    #     ) :
          
    #         self._set_rel_query(kwargs)
    #         return sa_orm.relationship(*args, **kwargs)
from flask_sqlalchemy import SQLAlchemy
    

db = SQLAlchemy()
# db.UUID = UUIDType  # type: ignore

def init_no_flask():
    engine = create_engine(os.environ.get("SQLALCHEMY_DATABASE_URI"))
    db.session = sessionmaker(bind=engine)()

def init_app(app):

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
    db.init_app(app)

    @app.teardown_request
    def _rollback_on_exception(exception=None):
        # A failed db.session.commit() (integrity error, etc.) leaves the
        # session's transaction in a state where any further query in the
        # same request raises PendingRollbackError, even though the DBAPI
        # transaction itself was already rolled back - SQLAlchemy requires
        # an explicit session.rollback() to reset the Session object's own
        # state before it's usable again. Several mutation call sites across
        # the codebase commit without a try/except around it, so this is a
        # safety net at the request boundary (guarantees the *next* request
        # never inherits a poisoned session) rather than a fix at every
        # individual call site within the same request.
        if exception is not None:
            db.session.rollback()

    with app.app_context():
        from hiddifypanel.panel.init_db import init_db
        init_db()



def db_execute(query: str, return_val: bool = False, commit: bool = False, **params):
    # print(params)
    q = db.session.execute(text(query), params)
    if commit:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    if return_val:
        return q.fetchall()

    # with db.engine.connect() as connection:
    #     res = connection.execute(text(query), params)
    #     connection.commit()s
    # return res


def backup_db() -> bool:
    import subprocess
    from loguru import logger
    dialect = db.engine.dialect.name
    url = str(db.engine.url)

    if dialect == 'sqlite':
        db_path_from_url = url.replace('sqlite:///', '')
        if db_path_from_url == ':memory:':
            return True
        backup_path = f"{db_path_from_url}.bak"
        logger.info(f"Backing up SQLite database to {backup_path}")
        res = subprocess.run(["sqlite3", db_path_from_url, f".backup '{backup_path}'"], capture_output=True)
        if res.returncode != 0:
            logger.error(f"SQLite backup failed: {res.stderr.decode()}")
            return False
        return True
    elif dialect == 'mysql':
        backup_path = "/opt/hiddify-manager/hiddify-panel/hiddifypanel.sql.bak"
        logger.info(f"Backing up MySQL database to {backup_path}")
        user = db.engine.url.username
        password = db.engine.url.password or ''
        database_name = db.engine.url.database
        host = db.engine.url.host
        cmd = ["mysqldump", "-h", str(host), "-u", str(user), f"-p{password}", str(database_name)]
        try:
            with open(backup_path, 'wb') as f:
                res = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
        except Exception as e:
            logger.error(f"MySQL backup failed to execute: {e}")
            return False

        if res.returncode != 0:
            logger.error(f"MySQL backup failed: {res.stderr.decode()}")
            return False
        return True

    logger.error(f"Unsupported dialect for backup: {dialect}")
    return False


def reconcile_schema() -> bool:
    """Additive-only runtime schema healer using Alembic's compare_metadata.

    Safety invariants:
    1. ADDITIVE-ONLY: creates missing tables/columns/indexes. Never drops or renames.
    2. FLAG AMBIGUOUS: any non-additive diff (type mismatch, extra column, rename) is logged as ERROR and aborts without stamping.
    3. PRE-DDL BACKUP: backup_db() must succeed before any DDL executes.

    Returns True if schema is clean (or healed), False if ambiguous diffs found or backup failed.
    """
    from loguru import logger
    from alembic.migration import MigrationContext
    from alembic.autogenerate import compare_metadata
    from sqlalchemy.schema import CreateTable, CreateIndex
    from sqlalchemy import text as sa_text

    # Explicitly closed once the diff is computed - MigrationContext holds
    # a reference cycle (dialect <-> connection <-> context) that defers
    # cleanup to the cyclic GC if left to a bare .connect(), so an
    # unclosed connection can sit checked out of the (Query)Pool - on a
    # file-backed SQLite engine that means a still-open transaction/
    # snapshot can later get handed back out for unrelated work.
    reflect_conn = db.engine.connect()
    try:
        context = MigrationContext.configure(reflect_conn)
        diff = compare_metadata(context, db.metadata)
    finally:
        reflect_conn.close()

    if not diff:
        # DEBUG, not INFO: this runs on every app startup (uwsgi worker
        # boot, `hiddify-panel-cli init-db` on every install.sh apply/
        # reinstall) and is the overwhelmingly common case - "nothing to
        # do" doesn't need to interrupt a normal install/apply's console
        # output. A real heal or an ambiguous diff (below) still logs at
        # INFO/ERROR since those are genuinely actionable.
        logger.debug("Schema perfectly matches models. No reconciliation needed.")
        return True

    ambiguous = False
    additive_ddl = []

    for op in diff:
        op_type = op[0]
        if op_type == 'add_table':
            table = op[1]
            additive_ddl.append(str(CreateTable(table).compile(db.engine)))
        elif op_type == 'add_column':
            # op: ('add_column', schema, table_name, column)
            table_name = op[2]
            column = op[3]
            # AddColumn lives in alembic.ddl.base, not sqlalchemy.schema -
            # SQLAlchemy core has no portable "ALTER TABLE ADD COLUMN" DDL
            # element of its own; alembic provides one (with per-dialect
            # @compiles handlers already registered on import).
            from alembic.ddl.base import AddColumn
            additive_ddl.append(str(AddColumn(table_name, column).compile(db.engine)))
        elif op_type == 'add_index':
            index = op[1]
            additive_ddl.append(str(CreateIndex(index).compile(db.engine)))
        else:
            ambiguous = True
            logger.error(f"Ambiguous schema diff detected (manual review required): {op}")

    if ambiguous:
        logger.error("Ambiguous schema differences found. Aborting reconciliation — no stamp applied.")
        return False

    if additive_ddl:
        logger.info(f"Reconciling {len(additive_ddl)} missing additive objects...")
        if not backup_db():
            logger.error("Pre-DDL backup failed. Aborting reconciliation.")
            return False

        with db.engine.connect() as conn:
            for ddl in additive_ddl:
                logger.info(f"Executing: {ddl}")
                conn.execute(sa_text(ddl))
            conn.commit()

    return True

