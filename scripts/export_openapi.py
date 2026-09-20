#!/usr/bin/env python3
"""Generate `docs/openapi.json` from the running application, or check it.

The routes, their response models and the error taxonomy are the normative description of
this API (ADR-0085). This script renders them as an OpenAPI document so that a client --
or `docs/api.md`'s examples -- can be checked against the contract, and `--check` fails the
build when the published file is not what the code produces.

Why generated rather than hand-authored, which is the same reason `export_ontology_schema.py`
gives: a hand-written contract beside a code implementation is two descriptions of one
thing, free to disagree. The disagreement surfaces as a client the document says is correct
and the server rejects, and nobody can say which is right.

`--self-test` runs first in CI, as every enforcement script here does. A check observed
only to pass has not been observed to work (DEF-0001).

Exit codes
----------
    0  the document is current (or was written with --write)
    1  the published document is stale, or the self-test failed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from causalog.api.app import create_app  # noqa: E402
from causalog.orchestration.identity import SignedTokenAuthenticator  # noqa: E402
from causalog.orchestration.wiring import Adapters  # noqa: E402
from causalog.persistence.memory.fakes import FixedClock  # noqa: E402

DOCUMENT_PATH = REPO_ROOT / "docs" / "openapi.json"

#: A fixed, obviously-fake secret. The application is built only to read its route table;
#: it serves nothing and connects to nothing, but the authenticator refuses a short secret
#: at construction, so one has to be supplied.
_RENDER_SECRET = "openapi-render-only-not-a-deployment-secret"  # noqa: S105


def render_document() -> str:
    """Return the OpenAPI document as canonical JSON text.

    Sorted keys and a fixed separator, for the reason `core.serialization` gives: two
    renders of one application must be byte-identical, or `--check` reports a diff that is
    purely a formatting artifact and everybody learns to ignore it.
    """
    clock = FixedClock()
    application = create_app(
        adapters=Adapters.in_memory(
            clock=clock,
            authenticator=SignedTokenAuthenticator(_RENDER_SECRET, clock),
            repository_root=REPO_ROOT,
        )
    )
    return json.dumps(application.openapi(), indent=2, sort_keys=True) + "\n"


def self_test() -> int:
    """Prove the check rejects a stale document before trusting it to accept a current one."""
    current = render_document()

    if not current.endswith("\n"):
        print(
            "SELF-TEST FAILED: rendered document does not end with exactly one newline."
        )
        return 1
    if render_document() != current:
        print(
            "SELF-TEST FAILED: two renders of one application differ; output is unstable."
        )
        return 1

    document = json.loads(current)
    if not document.get("paths"):
        print("SELF-TEST FAILED: the rendered document declares no paths.")
        return 1

    stale = current.replace('"openapi"', '"openapi_was_edited"', 1)
    if stale == current:
        print("SELF-TEST FAILED: could not construct a differing document to reject.")
        return 1
    if compare(stale, current) == 0:
        print("SELF-TEST FAILED: the comparison accepted a document it should reject.")
        return 1

    print(
        f"SELF-TEST PASSED: render is stable over {len(document['paths'])} path(s), and a "
        "modified document is rejected."
    )
    return 0


def compare(published: str, current: str) -> int:
    """Return 0 when the published document matches the current render, else 1."""
    return 0 if published == current else 1


def main() -> int:
    """Render the document, then write it, check it, or print it."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--self-test", action="store_true", help="prove the check rejects"
    )
    parser.add_argument(
        "--check", action="store_true", help="fail if the file is stale"
    )
    parser.add_argument("--write", action="store_true", help="write the file")
    arguments = parser.parse_args()

    if arguments.self_test:
        return self_test()

    current = render_document()

    if arguments.write:
        DOCUMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DOCUMENT_PATH.write_text(current, encoding="utf-8")
        print(f"wrote {DOCUMENT_PATH.relative_to(REPO_ROOT)}")
        return 0

    if arguments.check:
        if not DOCUMENT_PATH.is_file():
            print(
                f"{DOCUMENT_PATH.relative_to(REPO_ROOT)} does not exist. Run "
                "`python scripts/export_openapi.py --write`."
            )
            return 1
        published = DOCUMENT_PATH.read_text(encoding="utf-8")
        if compare(published, current) != 0:
            print(
                f"{DOCUMENT_PATH.relative_to(REPO_ROOT)} is STALE: it is not what the "
                "application produces. The document is generated, never edited by hand -- "
                "run `python scripts/export_openapi.py --write` and commit the result."
            )
            return 1
        print("OPENAPI: the published document matches the application.")
        return 0

    print(current, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
