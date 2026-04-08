"""External source connector framework.

Topgun AI federates retrieval over many *source families* (FIM, AMM,
IPC, WDM, SB, internal history). Some operators also have authorized
access to vendor / OEM portals — manufacturer manuals, parts websites,
fleet portals — that aren't ingested into the local index.

Rather than scraping those sites, we expose a clean ``Connector``
interface here. Each connector is a small adapter implemented per
authorized portal, and the registry is loaded explicitly. The default
shipping configuration is **empty** — no external sources are queried
unless an operator wires one in.

Public surface:

- :class:`Connector` — Protocol every adapter implements.
- :class:`ConnectorRegistry` — process-wide registry that the query
  engine consults.
- :func:`get_registry` — accessor used by the engine and tests.
- :class:`StubExternalConnector` — example/test connector that returns
  no hits but keeps the federation path exercised.
"""
from app.connectors.base import (
    Connector,
    ConnectorHit,
    ConnectorRegistry,
    StubExternalConnector,
    get_registry,
    set_registry,
)

__all__ = [
    "Connector",
    "ConnectorHit",
    "ConnectorRegistry",
    "StubExternalConnector",
    "get_registry",
    "set_registry",
]
