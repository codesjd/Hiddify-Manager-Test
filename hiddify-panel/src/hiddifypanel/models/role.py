"""This file isn't a model, it's just an enum for roles"""

from strenum import StrEnum


class Role(StrEnum):
    super_admin = "super_admin"
    admin = "admin"
    agent = "agent"
    user = "user"


class Permission(StrEnum):
    """Fine-grained permissions for AdminUser, on top of the coarse Role.

    super_admin implicitly has every permission regardless of what's in
    their `permissions` list. For admin/agent accounts: an EMPTY permissions
    list means "use the old role-only behavior" (full backward
    compatibility with every admin created before this existed) - only a
    NON-empty list actually restricts what they can do.

    Only a representative slice of endpoints check these so far (see
    Actions.py for restart/reinstall/status, DomainAdmin for domain CRUD).
    Extending coverage to every admin view is a mechanical follow-up: add
    `permissions={Permission.xxx}` to the relevant `login_required(...)`
    call.
    """

    view_traffic = "view_traffic"
    manage_users = "manage_users"
    manage_domains = "manage_domains"
    manage_settings = "manage_settings"
    restart_services = "restart_services"  # Actions: restart/status
    reinstall_apply = "reinstall_apply"  # Actions: apply/install/reinstall (more disruptive than a plain restart)


class AccountType(StrEnum):
    admin = "admin"
    user = "user"
