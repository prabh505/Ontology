# `deployment/sql/seeds`

**Single responsibility:** hold the minimal fixture rows a local database may be given,
mounted read-only at `/seeds` inside the PostgreSQL container.

Seeds are **not** applied automatically. `deployment/sql/migrations/` is the container's
init directory and runs on first initialization; seeds are applied deliberately, because a
fixture row that appears as a side effect of starting a container is indistinguishable
from a fact — and a fact with no evidence record cannot satisfy LAW-EVIDENCE.

Seeds carry no dataset content. Datasets are pinned by hash under `datasets/` and imported
through the Data Adapter (module 1), never side-loaded into the system of record.
