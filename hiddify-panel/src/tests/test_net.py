import os
import pytest
from unittest import mock
from hiddifypanel.hutils.network.net import is_ssh_password_authentication_enabled

@pytest.fixture
def mock_glob():
    with mock.patch("hiddifypanel.hutils.network.net.glob.glob") as mock_g:
        yield mock_g

def test_no_config_files(mock_glob):
    mock_glob.return_value = []
    assert is_ssh_password_authentication_enabled() is True

def test_password_auth_disabled(tmp_path, mock_glob):
    config_file = tmp_path / "sshd_config"
    config_file.write_text("PasswordAuthentication no\n")
    mock_glob.return_value = [str(config_file)]
    assert is_ssh_password_authentication_enabled() is False

def test_password_auth_enabled(tmp_path, mock_glob):
    config_file = tmp_path / "sshd_config"
    config_file.write_text("PasswordAuthentication yes\n")
    mock_glob.return_value = [str(config_file)]
    assert is_ssh_password_authentication_enabled() is True

def test_password_auth_disabled_case_insensitive(tmp_path, mock_glob):
    config_file = tmp_path / "sshd_config"
    config_file.write_text("pAsswordAuthentication nO\n")
    mock_glob.return_value = [str(config_file)]
    assert is_ssh_password_authentication_enabled() is False

def test_password_auth_disabled_with_spaces(tmp_path, mock_glob):
    config_file = tmp_path / "sshd_config"
    config_file.write_text("PasswordAuthentication \t no \n")
    mock_glob.return_value = [str(config_file)]
    assert is_ssh_password_authentication_enabled() is False

def test_commented_out(tmp_path, mock_glob):
    config_file = tmp_path / "sshd_config"
    config_file.write_text("# PasswordAuthentication no\n")
    mock_glob.return_value = [str(config_file)]
    assert is_ssh_password_authentication_enabled() is True

def test_commented_with_spaces_before(tmp_path, mock_glob):
    config_file = tmp_path / "sshd_config"
    config_file.write_text("  # PasswordAuthentication no\n")
    mock_glob.return_value = [str(config_file)]
    assert is_ssh_password_authentication_enabled() is True

def test_multiple_files_one_disabled(tmp_path, mock_glob):
    file1 = tmp_path / "sshd_config1"
    file1.write_text("Port 22\n")

    file2 = tmp_path / "sshd_config2"
    file2.write_text("PasswordAuthentication no\n")

    def glob_side_effect(pattern):
        if pattern == "/etc/ssh/sshd*":
            return [str(file1), str(file2)]
        return []

    mock_glob.side_effect = glob_side_effect
    assert is_ssh_password_authentication_enabled() is False

def test_file_read_error(tmp_path, mock_glob):
    config_file = tmp_path / "sshd_config"
    config_file.write_text("PasswordAuthentication no\n")
    mock_glob.return_value = [str(config_file)]

    with mock.patch("builtins.open", side_effect=PermissionError("Permission denied")):
        assert is_ssh_password_authentication_enabled() is True

def test_not_a_file(tmp_path, mock_glob):
    config_dir = tmp_path / "sshd_config.d"
    config_dir.mkdir()
    mock_glob.return_value = [str(config_dir)]
    assert is_ssh_password_authentication_enabled() is True
