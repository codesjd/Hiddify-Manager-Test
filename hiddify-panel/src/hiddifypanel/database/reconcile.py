import os
import subprocess
from loguru import logger
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from sqlalchemy import text
from hiddifypanel.database import db

def backup_db():
    dialect = db.engine.dialect.name
    url = str(db.engine.url)
    
    if dialect == 'sqlite':
        db_path = url.replace('sqlite:///', '')
        if db_path == ':memory:':
            return True
        backup_path = f"{db_path}.bak"
        logger.info(f"Backing up SQLite database to {backup_path}")
        res = subprocess.run(["sqlite3", db_path, f".backup '{backup_path}'"], capture_output=True)
        if res.returncode != 0:
            logger.error(f"SQLite backup failed: {res.stderr.decode()}")
            return False
        return True
    
    elif dialect == 'mysql':
        backup_path = "/opt/hiddify-manager/hiddify-panel/hiddifypanel.sql.bak"
        logger.info(f"Backing up MySQL database to {backup_path}")
        user = db.engine.url.username
        password = db.engine.url.password
        database = db.engine.url.database
        host = db.engine.url.host
        cmd = f"mysqldump -h {host} -u {user} -p{password} {database} > {backup_path}"
        res = subprocess.run(cmd, shell=True, capture_output=True)
        if res.returncode != 0:
            logger.error(f"MySQL backup failed: {res.stderr.decode()}")
            return False
        return True
    
    logger.error(f"Unsupported dialect for backup: {dialect}")
    return False

def reconcile_schema():
    context = MigrationContext.configure(db.engine.connect())
    diff = compare_metadata(context, db.metadata)
    
    if not diff:
        logger.info("Schema perfectly matches models. No reconciliation needed.")
        return True
        
    ambiguous = False
    additive_ddl = []
    
    for op in diff:
        op_type = op[0]
        if op_type == 'add_table':
            table = op[1]
            from sqlalchemy.schema import CreateTable
            additive_ddl.append(str(CreateTable(table).compile(db.engine)))
        elif op_type == 'add_column':
            # op: ('add_column', schema, table_name, column)
            table_name = op[2]
            column = op[3]
            from sqlalchemy.ext.compiler import compiles
            from sqlalchemy.schema import AddColumn
            additive_ddl.append(str(AddColumn(table_name, column).compile(db.engine)))
        elif op_type == 'add_index':
            index = op[1]
            from sqlalchemy.schema import CreateIndex
            additive_ddl.append(str(CreateIndex(index).compile(db.engine)))
        else:
            ambiguous = True
            logger.error(f"Ambiguous diff detected: {op}")
            
    if ambiguous:
        logger.error("Ambiguous schema differences (drops/renames/type changes) found. Manual review required. Aborting reconciliation.")
        return False
        
    if additive_ddl:
        logger.info(f"Reconciling {len(additive_ddl)} missing additive objects...")
        if not backup_db():
            return False
            
        with db.engine.connect() as conn:
            for ddl in additive_ddl:
                logger.info(f"Executing: {ddl}")
                conn.execute(text(ddl))
            conn.commit()
            
    return True
