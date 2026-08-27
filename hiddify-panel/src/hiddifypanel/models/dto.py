"""Typed data-transfer objects for the bulk_register / add_or_update path.

These are plain dataclasses (NOT SQLAlchemy models) used to carry the
values coming from cross-node sync/register payloads and JSON backups into
the model `add_or_update` methods with attribute access instead of raw
dicts. `_as_dto` bridges the two: a dict is filtered to the DTO's own
fields and constructed into the DTO; anything that is already a DTO (or any
non-Mapping object) is passed through unchanged, so callers can pass either
form during migration.

Every field defaults to None so a partial payload (e.g. a config row that
only carries key/value) still constructs, and `add_or_update` can treat
None as "not provided, leave the existing DB value alone" - matching the
`data.get(...) is not None` semantics the dict-based code used before.
"""
import dataclasses
from collections.abc import Mapping
from typing import Any


@dataclasses.dataclass
class BaseAccountDTO:
    uuid: Any = None
    name: Any = None
    comment: Any = None
    telegram_id: Any = None
    lang: Any = None


@dataclasses.dataclass
class UserDTO(BaseAccountDTO):
    usage_limit_GB: Any = None
    usage_limit: Any = None
    package_days: Any = None
    mode: Any = None
    last_online: Any = None
    start_date: Any = None
    current_usage_GB: Any = None
    current_usage: Any = None
    last_reset_time: Any = None
    added_by_uuid: Any = None
    ed25519_private_key: Any = None
    ed25519_public_key: Any = None
    wg_pk: Any = None
    wg_pub: Any = None
    wg_psk: Any = None
    enable: Any = None
    is_active: Any = None
    id: Any = None


@dataclasses.dataclass
class AdminUserDTO(BaseAccountDTO):
    mode: Any = None
    can_add_admin: Any = None
    parent_admin_uuid: Any = None
    max_users: Any = None
    max_active_users: Any = None
    id: Any = None


@dataclasses.dataclass
class ChildDTO:
    id: Any = None
    name: Any = None
    mode: Any = None
    unique_id: Any = None


@dataclasses.dataclass
class DomainDTO:
    domain: Any = None
    mode: Any = None
    sub_link_only: Any = None
    cdn_ip: Any = None
    alias: Any = None
    grpc: Any = None
    servernames: Any = None
    resolve_ip: Any = None
    extra_params: Any = None
    http_port: Any = None
    tls_port: Any = None
    reality_port: Any = None
    reality_private_key: Any = None
    reality_public_key: Any = None
    reality_short_id: Any = None
    show_domains: Any = None
    download_domain: Any = None
    child_unique_id: Any = None
    child_id: Any = None


@dataclasses.dataclass
class ProxyDTO:
    name: Any = None
    enable: Any = None
    proto: Any = None
    transport: Any = None
    cdn: Any = None
    l3: Any = None
    params: Any = None
    child_unique_id: Any = None


@dataclasses.dataclass
class HConfigDTO:
    key: Any = None
    value: Any = None
    child_unique_id: Any = None


def _as_dto(x, DTO):
    """Coerce `x` into an instance of dataclass `DTO`.

    - If `x` is a Mapping (dict), keep only the keys that are actual DTO
      fields and construct the DTO from them (unknown keys are dropped,
      missing keys fall back to the field defaults).
    - Otherwise `x` is assumed to already be a DTO (or a model exposing the
      same attributes) and is returned unchanged.
    """
    if not isinstance(x, Mapping):
        return x
    allowed = {f.name for f in dataclasses.fields(DTO)}
    return DTO(**{k: v for k, v in x.items() if k in allowed})
