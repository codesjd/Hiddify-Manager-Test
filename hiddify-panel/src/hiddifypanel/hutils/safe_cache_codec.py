"""JSON-based, allowlist-only (de)serializer for the Redis cache in cache.py.

pickle.loads() can execute arbitrary code via a crafted __reduce__ payload
for anything it deserializes. This cache's data source is Redis, and while
this codebase's default redis.conf binds to 127.0.0.1 with a password (not
remotely reachable today), that's not a reason to keep an RCE-shaped
deserializer as the thing standing between "someone got local/Redis access"
and "arbitrary code execution in the panel process".

This module speaks only JSON on the wire (parsing JSON cannot execute code)
and reconstructs objects through a fixed allowlist of classes built once by
scanning hiddifypanel.models - the decoder only ever does a dict lookup
against that pre-built allowlist, never a dynamic import/getattr driven by
a string that came off the wire.
"""
import enum
import ipaddress
import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import instrumentation

from hiddifypanel.database import db

_IP_TYPES = (
    ipaddress.IPv4Address,
    ipaddress.IPv6Address,
    ipaddress.IPv4Network,
    ipaddress.IPv6Network,
)


def _is_enum_like(obj: Any) -> bool:
    if isinstance(obj, enum.Enum):
        return True
    name = getattr(obj, 'name', None)
    if name is None:
        return False
    cls = type(obj)
    try:
        # Works for both stdlib Enum and the FastEnum metaclass (ConfigEnum,
        # ConfigCategory): both support cls[member_name] -> member instance.
        return cls[name] is obj
    except Exception:
        return False


def _model_columns(cls: type) -> list[str]:
    return [c.key for c in sa_inspect(cls).mapper.column_attrs]


_ALLOWLIST: dict[str, type] | None = None


def _allowlist() -> dict[str, type]:
    global _ALLOWLIST
    if _ALLOWLIST is not None:
        return _ALLOWLIST

    # Imported lazily (not at module load time) since hiddifypanel.models
    # itself imports hiddifypanel.cache (for the @cache.cache decorator) -
    # importing it eagerly here would be a circular import at load time.
    import hiddifypanel.models as models_pkg

    allowlist: dict[str, type] = {}
    for name in dir(models_pkg):
        if name.startswith('_'):
            continue
        obj = getattr(models_pkg, name)
        if not isinstance(obj, type):
            continue
        is_model = False
        try:
            is_model = issubclass(obj, db.Model)
        except TypeError:
            pass
        is_enum = issubclass(obj, enum.Enum) or hasattr(obj, '_value_to_instance_map')
        if is_model or is_enum:
            allowlist[obj.__name__] = obj
    _ALLOWLIST = allowlist
    return allowlist


def _encode(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, db.Model):
        cls = type(obj)
        cols = _model_columns(cls)
        return {'__t': 'model', 'cls': cls.__name__, 'data': {c: _encode(getattr(obj, c)) for c in cols}}
    if _is_enum_like(obj):
        return {'__t': 'enum', 'cls': type(obj).__name__, 'name': obj.name}
    if isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, datetime):
        return {'__t': 'datetime', 'v': obj.isoformat()}
    if isinstance(obj, date):
        return {'__t': 'date', 'v': obj.isoformat()}
    if isinstance(obj, _IP_TYPES):
        return {'__t': 'ipaddress', 'v': str(obj)}
    if isinstance(obj, tuple):
        return {'__t': 'tuple', 'v': [_encode(v) for v in obj]}
    if isinstance(obj, (set, frozenset)):
        return {'__t': 'set', 'v': [_encode(v) for v in obj]}
    if isinstance(obj, (list,)):
        return [_encode(v) for v in obj]
    if isinstance(obj, dict):
        # type(k) is str (not isinstance) on purpose: StrEnum members are
        # also `isinstance(x, str)`, and routing them through the plain
        # "dict" tag below would silently drop the key straight to a bare
        # str via JSON, losing the enum type on round-trip.
        if all(type(k) is str for k in obj):
            return {'__t': 'dict', 'v': {k: _encode(v) for k, v in obj.items()}}
        return {'__t': 'dict_pairs', 'v': [[_encode(k), _encode(v)] for k, v in obj.items()]}
    # Best-effort fallback: never let one unrepresentable value blow up the
    # whole cached call - matches this cache's existing "log and move on"
    # philosophy elsewhere in this file.
    return {'__t': 'unrepresentable', 'v': repr(obj)}


def _decode(obj: Any) -> Any:
    if isinstance(obj, list):
        return [_decode(v) for v in obj]
    if not isinstance(obj, dict):
        return obj

    tag = obj.get('__t')
    if tag is None:
        return {k: _decode(v) for k, v in obj.items()}
    if tag == 'dict':
        return {k: _decode(v) for k, v in obj['v'].items()}
    if tag == 'dict_pairs':
        return {_decode(k): _decode(v) for k, v in obj['v']}
    if tag == 'tuple':
        return tuple(_decode(v) for v in obj['v'])
    if tag == 'set':
        return {_decode(v) for v in obj['v']}
    if tag == 'datetime':
        return datetime.fromisoformat(obj['v'])
    if tag == 'date':
        return date.fromisoformat(obj['v'])
    if tag == 'ipaddress':
        return ipaddress.ip_address(obj['v']) if '/' not in obj['v'] else ipaddress.ip_network(obj['v'])
    if tag == 'enum':
        cls = _allowlist().get(obj['cls'])
        if cls is None:
            return None
        try:
            return cls[obj['name']]
        except Exception:
            return None
    if tag == 'model':
        cls = _allowlist().get(obj['cls'])
        if cls is None:
            return None
        # cls.__new__(cls) would skip SQLAlchemy's instrumentation setup
        # (no _sa_instance_state), so attribute assignment below would
        # crash - ClassManager.new_instance() is the same mechanism the
        # ORM's own loader uses to build instances without calling
        # __init__.
        manager = instrumentation.manager_of_class(cls)
        instance = manager.new_instance()
        for k, v in obj['data'].items():
            setattr(instance, k, _decode(v))
        return instance
    if tag == 'unrepresentable':
        return obj['v']
    return {k: _decode(v) for k, v in obj.items()}


def dumps(obj: Any) -> bytes:
    return json.dumps(_encode(obj)).encode('utf-8')


def loads(data: bytes) -> Any:
    return _decode(json.loads(data))
