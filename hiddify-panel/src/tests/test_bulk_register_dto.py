"""Sync/backup smoke tests for the bulk_register / add_or_update DTO refactor.

These cover the two real code paths that consume the DTO machinery:
  * BACKUP restore : hiddify.set_db_from_json(dump_db_to_dict()) roundtrip,
                     which drives every model's bulk_register() from plain
                     dicts.
  * SYNC           : bulk_register(..., remove=True) parent->child semantics,
                     plus DTO-object passthrough and dict backward-compat.

The `app` fixture (tests/conftest.py) is session-scoped and seeds the schema,
default configs and the owner admin; every check below uses fresh UUIDs so it
is independent of whatever other suite files leave behind.
"""
import json
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def _clean_session(app):
    """The `app` fixture is session-scoped and shares one db.session across
    the whole suite, so an earlier test that leaves a failed transaction open
    would surface here as an unrelated PendingRollbackError. Roll back before
    and after each test so these checks stand on a clean session and never
    leak one of their own."""
    from hiddifypanel.database import db
    db.session.rollback()
    yield
    db.session.rollback()


def _seed(db, owner_id, child_id, models):
    User, Domain, Proxy = models
    from hiddifypanel.models.domain import DomainType
    from hiddifypanel.models.proxy import ProxyProto, ProxyTransport, ProxyCDN, ProxyL3
    u_uuid = str(uuid4())
    db.session.add(User(uuid=u_uuid, name='backup_user', usage_limit_GB=42,
                        package_days=30, added_by=owner_id, comment='keep-me'))
    dom = f'smoke-{uuid4().hex[:8]}.example.com'
    db.session.add(Domain(domain=dom, mode=DomainType.direct, child_id=child_id))
    pname = f'smoke-proxy-{uuid4().hex[:6]}'
    db.session.add(Proxy(name=pname, proto=ProxyProto.vless, transport=ProxyTransport.WS,
                         cdn=ProxyCDN.direct, l3=ProxyL3.tls, enable=True, child_id=child_id))
    db.session.commit()
    return u_uuid, dom, pname


def test_backup_roundtrip_restores_all_models(app):
    from hiddifypanel.database import db
    from hiddifypanel.models import User, Domain, Proxy, Child, ConfigEnum, hconfig, set_hconfig, AdminUser
    from hiddifypanel.panel import hiddify

    owner = AdminUser.get_super_admin()
    child_id = Child.current().id
    u_uuid, dom, pname = _seed(db, owner.id, child_id, (User, Domain, Proxy))
    set_hconfig(ConfigEnum.branding_title, 'SMOKE-BRAND')
    db.session.commit()

    backup = hiddify.dump_db_to_dict()
    assert any(x['uuid'] == u_uuid for x in backup['users'])

    # wipe the seeded rows and clobber the config
    User.query.filter(User.uuid == u_uuid).delete()
    Domain.query.filter(Domain.domain == dom).delete()
    Proxy.query.filter(Proxy.name == pname).delete()
    set_hconfig(ConfigEnum.branding_title, 'WIPED')
    db.session.commit()
    assert User.query.filter(User.uuid == u_uuid).first() is None

    # restore from the JSON backup: drives bulk_register from dicts
    hiddify.set_db_from_json(backup, override_child_unique_id=False, override_root_admin=False)
    db.session.commit()

    ru = User.query.filter(User.uuid == u_uuid).first()
    assert ru is not None
    assert ru.name == 'backup_user' and int(ru.usage_limit_GB) == 42 and ru.comment == 'keep-me'
    assert Domain.query.filter(Domain.domain == dom).first() is not None
    assert Proxy.query.filter(Proxy.name == pname).first() is not None
    assert hconfig(ConfigEnum.branding_title) == 'SMOKE-BRAND'


def test_backup_roundtrip_restores_domain_with_extra_params(app):
    """extra_params is a String column but to_dict()/JSON-backup emit it as a
    parsed dict. add_or_update must re-encode it so restore doesn't crash with
    'type dict is not supported'."""
    from hiddifypanel.database import db
    from hiddifypanel.models import Domain, Child
    from hiddifypanel.models.domain import DomainType
    from hiddifypanel.panel import hiddify

    dom = f'extra-{uuid4().hex[:8]}.example.com'
    d = Domain(domain=dom, mode=DomainType.direct, child_id=Child.current().id)
    d.extra_params = json.dumps({'xdns_resolvers': '9.9.9.9:53'})
    db.session.add(d)
    db.session.commit()

    backup = hiddify.dump_db_to_dict()
    entry = next(x for x in backup['domains'] if x['domain'] == dom)
    assert isinstance(entry['extra_params'], dict)  # to_dict emits a dict

    Domain.query.filter(Domain.domain == dom).delete()
    db.session.commit()

    # must not raise
    hiddify.set_db_from_json(backup, override_child_unique_id=False, override_root_admin=False)
    db.session.commit()

    restored = Domain.query.filter(Domain.domain == dom).first()
    assert restored is not None
    assert restored.extra_params_json().get('xdns_resolvers') == '9.9.9.9:53'


def test_sync_bulk_register_dict_and_remove(app):
    from hiddifypanel.database import db
    from hiddifypanel.models import User, AdminUser
    owner = AdminUser.get_super_admin()

    keep = str(uuid4())
    stale = str(uuid4())
    db.session.add(User(uuid=stale, name='stale', usage_limit_GB=1, package_days=1, added_by=owner.id))
    db.session.commit()

    User.bulk_register([{'uuid': keep, 'name': 'synced', 'usage_limit_GB': 7,
                         'package_days': 10, 'added_by_uuid': owner.uuid}],
                       commit=True, remove=True)

    assert User.query.filter(User.uuid == keep).first().name == 'synced'
    # remove=True prunes users not present in the payload
    assert User.query.filter(User.uuid == stale).first() is None


def test_sync_bulk_register_accepts_dto_objects(app):
    from hiddifypanel.models import User, AdminUser
    from hiddifypanel.models.dto import UserDTO
    owner = AdminUser.get_super_admin()

    from hiddifypanel.models.user import UserMode
    dto_uuid = str(uuid4())
    User.bulk_register([UserDTO(uuid=dto_uuid, name='dto_user', usage_limit_GB=3,
                                package_days=5, mode=UserMode.weekly,
                                added_by_uuid=owner.uuid)],
                       commit=True, remove=False)
    du = User.query.filter(User.uuid == dto_uuid).first()
    assert du is not None and du.name == 'dto_user'
    # mode must propagate through the DTO (_dto) path, not just the dict path
    assert du.mode == UserMode.weekly


def test_partial_update_preserves_unspecified_fields(app):
    from hiddifypanel.database import db
    from hiddifypanel.models import User, AdminUser
    owner = AdminUser.get_super_admin()

    uuid = str(uuid4())
    User.bulk_register([{'uuid': uuid, 'name': 'orig', 'usage_limit_GB': 4,
                         'package_days': 5, 'added_by_uuid': owner.uuid}], commit=True)

    # dict path with only comment: name/usage must be preserved, not nulled
    User.add_or_update(uuid=uuid, comment='partial-only')
    db.session.commit()

    u = User.query.filter(User.uuid == uuid).first()
    assert u.name == 'orig' and u.comment == 'partial-only' and int(u.usage_limit_GB) == 4


def test_domain_sync_via_schema_shaped_dict(app):
    """DomainSchema omits extra_params, so the cross-node sync payload never
    carries the dict that the backup path has to re-encode."""
    from hiddifypanel.models import Domain
    dom = f'synced-{uuid4().hex[:8]}.example.com'
    Domain.bulk_register([{'domain': dom, 'mode': 'direct', 'sub_link_only': False,
                           'grpc': False, 'cdn_ip': '', 'alias': '', 'servernames': '',
                           'show_domains': []}], commit=True)
    assert Domain.query.filter(Domain.domain == dom).first() is not None


def test_as_dto_coercion_contract(app):
    from hiddifypanel.models.dto import _as_dto, UserDTO
    coerced = _as_dto({'uuid': 'x', 'name': 'n', 'bogus_key': 1}, UserDTO)
    assert isinstance(coerced, UserDTO) and coerced.uuid == 'x' and coerced.name == 'n'
    passthru = _as_dto(UserDTO(uuid='y'), UserDTO)
    assert passthru.uuid == 'y'
