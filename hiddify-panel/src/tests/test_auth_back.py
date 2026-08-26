import pytest
from unittest.mock import patch, MagicMock
from hiddifypanel.panel.auth_back import verify_basic_auth_password

def test_verify_basic_auth_password_empty_credentials(app):
    with app.app_context():
        assert verify_basic_auth_password(None, "password") is None
        assert verify_basic_auth_password("user", None) is None
        assert verify_basic_auth_password("", "password") is None
        assert verify_basic_auth_password("user", "") is None
        assert verify_basic_auth_password(None, None) is None
        assert verify_basic_auth_password("", "") is None

@patch('hiddifypanel.panel.auth_back.User.by_username_password')
@patch('hiddifypanel.panel.auth_back.AdminUser.by_username_password')
def test_verify_basic_auth_password_not_found(mock_admin_by_up, mock_user_by_up, app):
    with app.app_context():
        mock_user_by_up.return_value = None
        mock_admin_by_up.return_value = None

        result = verify_basic_auth_password("unknown_user", "wrong_pass")

        assert result is None
        mock_user_by_up.assert_called_once_with("unknown_user", "wrong_pass")
        mock_admin_by_up.assert_called_once_with("unknown_user", "wrong_pass")

@patch('hiddifypanel.panel.auth_back.User.by_username_password')
@patch('hiddifypanel.panel.auth_back.AdminUser.by_username_password')
def test_verify_basic_auth_password_user_found(mock_admin_by_up, mock_user_by_up, app):
    with app.app_context():
        mock_user = MagicMock()
        mock_user_by_up.return_value = mock_user
        mock_admin_by_up.return_value = None

        result = verify_basic_auth_password("real_user", "correct_pass")

        assert result is mock_user
        mock_user_by_up.assert_called_once_with("real_user", "correct_pass")
        mock_admin_by_up.assert_not_called()

@patch('hiddifypanel.panel.auth_back.User.by_username_password')
@patch('hiddifypanel.panel.auth_back.AdminUser.by_username_password')
def test_verify_basic_auth_password_admin_found(mock_admin_by_up, mock_user_by_up, app):
    with app.app_context():
        mock_admin = MagicMock()
        mock_user_by_up.return_value = None
        mock_admin_by_up.return_value = mock_admin

        result = verify_basic_auth_password("admin_user", "admin_pass")

        assert result is mock_admin
        mock_user_by_up.assert_called_once_with("admin_user", "admin_pass")
        mock_admin_by_up.assert_called_once_with("admin_user", "admin_pass")
