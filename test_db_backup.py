import subprocess
from unittest.mock import patch, MagicMock

import hiddifypanel.database as db_module
from sqlalchemy import create_engine

class MockEngine:
    def __init__(self, dialect_name):
        self.dialect = MagicMock()
        self.dialect.name = dialect_name
        self.url = MagicMock()
        self.url.username = "test_user"
        self.url.password = "test_pass"
        self.url.database = "test_db"
        self.url.host = "localhost"
        self.url.__str__ = lambda x: f"{dialect_name}://localhost/test_db"

def test_mysql_backup_security():
    db_module.db = MagicMock()
    db_module.db.engine = MockEngine('mysql')

    with patch('subprocess.run') as mock_run:
        with patch('builtins.open', MagicMock()) as mock_open:
            mock_run.return_value.returncode = 0

            result = db_module.backup_db()

            assert result == True
            # Verify subprocess.run was called with a list, NOT a string and NO shell=True
            args, kwargs = mock_run.call_args
            assert isinstance(args[0], list), f"Expected list for subprocess.run args, got {type(args[0])}"
            assert args[0] == ["mysqldump", "-h", "localhost", "-u", "test_user", "-ptest_pass", "test_db"]
            assert 'shell' not in kwargs or kwargs['shell'] == False
            assert 'stdout' in kwargs
            assert kwargs['stderr'] == subprocess.PIPE

if __name__ == "__main__":
    test_mysql_backup_security()
    print("Test passed successfully!")
