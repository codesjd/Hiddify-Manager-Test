"""Opt-in periodic rotation of the panel-wide uTLS fingerprint
(ConfigEnum.utls) among real-browser mimicry choices.

Deliberately a different mechanism from utls's own "random"/"randomized"
choices: those vary the ClientHello per-connection, which is what a single
real browser never does. This instead holds one stable value for
utls_rotate_days at a time, then swaps it for a different stable value -
the goal isn't to look unpredictable within a session, it's to stop
presenting the exact same fingerprint indefinitely so static blocklists
keyed on a captured JA3/SNI/IP tuple age out. A random jitter is applied
around the configured interval so the swap itself doesn't land on an
exactly predictable cadence, which would be its own distinguishing
pattern.
"""
import random
from datetime import datetime, timedelta, timezone

from celery import shared_task
from loguru import logger

from hiddifypanel.models import ConfigEnum, hconfig, set_hconfig
from hiddifypanel import hutils
from hiddifypanel.panel.run_commander import Command, commander

# Real browser-mimicry choices only - mirrors SettingAdmin.py's utls
# SelectField minus "none"/"random"/"randomized", which are the separate
# per-connection mechanisms described above and aren't touched here.
FINGERPRINT_POOL = ("chrome", "edge", "ios", "android", "safari", "firefox")

# +/- this fraction of utls_rotate_days, so rotations don't happen on an
# exactly predictable clock.
_JITTER_FRACTION = 0.2
_MIN_ROTATE_DAYS = 1


def _parse_last_rotated_at(raw: str | None) -> "datetime | None":
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _is_rotation_due(rotate_days: int, last_rotated_at: "datetime | None", now: datetime) -> bool:
    if last_rotated_at is None:
        return True
    jitter_days = rotate_days * _JITTER_FRACTION
    due_at = last_rotated_at + timedelta(days=rotate_days - jitter_days)
    return now >= due_at


@shared_task(ignore_result=True)
def rotate_utls_fingerprint_if_due() -> None:
    if not hconfig(ConfigEnum.utls_auto_rotate):
        return

    rotate_days = hconfig(ConfigEnum.utls_rotate_days) or _MIN_ROTATE_DAYS
    if rotate_days < _MIN_ROTATE_DAYS:
        rotate_days = _MIN_ROTATE_DAYS

    now = datetime.now(timezone.utc)
    last_rotated_at = _parse_last_rotated_at(hconfig(ConfigEnum.utls_last_rotated_at))
    if not _is_rotation_due(rotate_days, last_rotated_at, now):
        return

    current = hconfig(ConfigEnum.utls)
    # If the current value isn't one of the pool (admin picked "none"/
    # "random"/"randomized", or something custom), any pool member is a
    # valid first pick - there's nothing to exclude.
    choices = [f for f in FINGERPRINT_POOL if f != current] or list(FINGERPRINT_POOL)
    new_fingerprint = random.choice(choices)

    from hiddifypanel.database import db
    set_hconfig(ConfigEnum.utls, new_fingerprint, commit=False)
    set_hconfig(ConfigEnum.utls_last_rotated_at, now.isoformat(), commit=False)
    db.session.commit()

    logger.info(f"utls auto-rotate: {current!r} -> {new_fingerprint!r}")

    # Applied directly and narrowly (xray+singbox only - utls only affects
    # those two cores' own generated inbound/outbound templates) instead of
    # going through apply_scope.mark_dirty()/clear_pending_subsystems():
    # this rotation's effect is already fully captured by the commander()
    # call below, so there's nothing left to "remember" for a later apply -
    # and touching the shared pending-subsystems bookkeeping here could
    # wipe out an unrelated admin change (e.g. a still-pending domain edit)
    # that's genuinely waiting for the admin's own next Apply Configs click.
    commander(Command.apply, subsystems=hutils.apply_scope.CORE_ONLY_SUBSYSTEMS)
