"""Generic outgoing webhook support.

Independent of the Telegram bot notifications (see panel/usage.py
send_bot_message). Lets you point Hiddify at your own HTTP endpoint (a
monitoring service, another one of your own servers, n8n, etc.) and get a
POSTed JSON payload whenever a user's active/inactive status flips - i.e.
traffic limit hit, expired, or renewed/reactivated.

Configured via three settings (Panel Settings admin page):
  - webhook_enable: master on/off switch
  - webhook_url: destination URL (only a single URL for now; comma-split
    yourself and loop if you need more than one)
  - webhook_signing_key: optional. If set, every request carries an
    X-Hiddify-Signature header = hex HMAC-SHA256(secret, raw_json_body), so
    your receiver can verify the request actually came from this panel.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from loguru import logger


def _do_post(url: str, payload: dict, secret: str | None):
    import hashlib
    import hmac

    import requests

    body = json.dumps(payload, default=str)
    headers = {"Content-Type": "application/json"}
    if secret:
        sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        headers["X-Hiddify-Signature"] = sig

    for attempt in range(3):
        try:
            resp = requests.post(url, data=body, headers=headers, timeout=5)
            if resp.status_code >= 400:
                logger.warning(f"webhook POST to {url} returned {resp.status_code}: {resp.text[:200]}")
            return
        except Exception as e:
            if attempt == 2:
                logger.warning(f"webhook POST to {url} failed after 3 attempts: {e}")
            else:
                time.sleep(1.5 * (attempt + 1))


def send_webhook_event(event_type: str, data: dict[str, Any]) -> None:
    """Fire-and-forget a webhook event. Never raises - a broken/unreachable
    webhook endpoint must never interrupt usage processing or any other
    caller. Runs the actual HTTP call in a background thread so callers
    (e.g. the celery usage-update task) don't block on a slow endpoint.
    """
    try:
        from hiddifypanel.models import ConfigEnum, hconfig

        if not hconfig(ConfigEnum.webhook_enable):
            return
        url = hconfig(ConfigEnum.webhook_url)
        if not url:
            return
        secret = hconfig(ConfigEnum.webhook_signing_key) or None
        payload = {
            "event": event_type,
            "timestamp": time.time(),
            "data": data,
        }
        t = threading.Thread(target=_do_post, args=(url, payload, secret), daemon=True)
        t.start()
    except Exception:
        logger.exception("send_webhook_event failed (non-fatal)")
