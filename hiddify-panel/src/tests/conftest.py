import os
os.environ['STDOUT_LOG_LEVEL'] = 'INFO'
os.environ['REDIS_URI_MAIN'] = 'redis://127.0.0.1:6379'
os.environ['REDIS_URI_SSE'] = 'redis://127.0.0.1:6379'
os.environ['HIDDIFY_CONFIG_PATH'] = '/opt/hiddify-manager'
import pytest

from hiddifypanel import create_app


@pytest.fixture(scope='session')
def app(tmp_path_factory):
    """Single shared Flask app for the whole tests/ suite.

    Flask blueprints (e.g. common_bp) are module-level singletons that flag
    themselves as registered on first use and raise AssertionError if
    create_app() is called a second time in the same process - so every
    test file must depend on this one fixture rather than defining its own.

    File-backed (not ':memory:') so tests that shell out to real DB tooling
    (e.g. reconcile_schema()'s pre-DDL backup via the sqlite3 CLI, which
    no-ops on ':memory:') can exercise the real path.
    """
    db_path = tmp_path_factory.mktemp("hiddify_test") / "test.db"
    app = create_app(
        SQLALCHEMY_DATABASE_URI=f'sqlite:///{db_path}', TESTING=True,
        STDOUT_LOG_LEVEL='INFO', HIDDIFY_CONFIG_PATH='/opt/hiddify-manager',
        REDIS_URI_MAIN='redis://127.0.0.1:6379', REDIS_URI_SSE='redis://127.0.0.1:6379',
    )
    app.config['_TEST_DB_PATH'] = db_path
    with app.app_context():
        yield app


@pytest.fixture(scope='session')
def db_path(app):
    return app.config['_TEST_DB_PATH']
