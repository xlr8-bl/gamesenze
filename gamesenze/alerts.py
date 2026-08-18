"""Alerting.

§8 says failure must never be silent. That is only true if the alert path
itself is reliable, so this module never raises: an alert that fails to send
logs loudly and lets the job finish, rather than turning a warning into an
outage.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

log = logging.getLogger("gamesenze.alerts")


class Alerter:
    def __init__(self, webhook_url: str = "", *, timeout: float = 10.0) -> None:
        self._url = webhook_url
        self._timeout = timeout
        self.sent: list[dict[str, Any]] = []

    def alert(self, message: str, **context: Any) -> None:
        payload = {"text": message, **context}
        self.sent.append(payload)
        log.warning("ALERT: %s %s", message, context or "")
        if not self._url:
            return
        try:
            request = urllib.request.Request(
                self._url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(request, timeout=self._timeout).close()
        except Exception as exc:  # noqa: BLE001 - never let alerting break a job
            log.error("alert delivery failed: %s", exc)
