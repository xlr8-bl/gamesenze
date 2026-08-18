"""Self-collected data — §4.

The deepest data is not behind an API, it is on public web pages. We collect it
ourselves, and we do it politely: 6 seconds between requests to a host, an
honest User-Agent with a contact address, off-peak hours, and aggressive
caching so we never re-fetch what has not changed.
"""

from .throttle import HostThrottle, off_peak_now

__all__ = ["HostThrottle", "off_peak_now"]
