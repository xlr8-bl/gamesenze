"""Vendor API clients.

Every client here goes through `MeteredClient`, which reserves budget before
the request and stores the raw response after it. Neither is optional:
REQ-BUDGET-3 depends on the first and REQ-SCRAPE-5 on the second.
"""

from .base import MeteredClient, Response, Transport

__all__ = ["MeteredClient", "Response", "Transport"]
