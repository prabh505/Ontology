"""The module `uvicorn` points at: an application wired to real adapters.

Separate from `app.py` because `create_app` takes its adapters and this is the one place
that decides to build the REAL ones. A module-level `app = create_app(adapters=...)` inside
`app.py` would connect to PostgreSQL, Neo4j and Redis on import -- including when a test
imports it to read the route table, which is how a test suite writes to a production
database once.

Importing this module therefore has side effects by design: it reads the environment and
opens the configuration it names. Nothing in the test suite imports it.
"""

from __future__ import annotations

from causalog.api.app import create_app
from causalog.orchestration.wiring import Adapters

__all__ = ["app"]

app = create_app(adapters=Adapters.from_environment())
