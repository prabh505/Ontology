"""The projection content hash is stable across processes (`CONVENTIONS.md` §11).

`docs/architecture.md` §3.3 step 6 compares a rebuild's hash against the previous build's
and calls a difference a determinism defect. That comparison is only meaningful if the hash
is a function of the content and of nothing else -- not of dict iteration, not of insertion
sequence, not of `PYTHONHASHSEED`, and not of the namespace the build happened to land in.

The fresh-interpreter check is the one that matters. Python's `hash()` is randomised per
process unless the seed is pinned, and a hash computed with it would agree with itself all
day inside one test session and disagree with the build from ten minutes ago. That failure
looks exactly like a real determinism defect, which is the expensive kind of false alarm.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from causalog.core.run import RunKey
from tests.fixtures import facts

pytestmark = pytest.mark.determinism


def _seeded_projection() -> None:
    from causalog.persistence.memory import InMemoryFactRepository, InMemoryGraphProjection

    repository = InMemoryFactRepository()
    citation = facts.evidence_record("row:1")
    repository.write_evidence_records([citation])
    participant = facts.entity("P1", citation=citation)
    repository.write_entities([participant], facts.ONTOLOGY_HASH)
    events = [
        facts.event(
            f"STAGE_{index}",
            facts.interval(index),
            citation=citation,
            participants=(participant,),
        )
        for index in range(6)
    ]
    repository.write_events(events, facts.ONTOLOGY_HASH)
    run_id = repository.register_run(
        RunKey(
            dataset_version=facts.DATASET_VERSION,
            ontology_hash=facts.ONTOLOGY_HASH,
            rule_pack_version="1.0.0",
            engine_version="0.1.0",
            seed=0,
        )
    )
    repository.write_causal_edges(
        [facts.causal_edge(events[index], events[index + 1], run_id) for index in range(5)]
    )
    return InMemoryGraphProjection(repository=repository), run_id


def test_the_hash_does_not_depend_on_write_sequence() -> None:
    """Same facts written in a different sequence must hash the same.

    The projection sorts its token stream before hashing precisely so this holds. Without
    the sort, the hash would encode the sequence a caller happened to iterate in, and two
    correct pipelines would disagree.
    """
    from causalog.persistence.memory import InMemoryFactRepository, InMemoryGraphProjection

    forward, run_id = _seeded_projection()

    reversed_repository = InMemoryFactRepository()
    citation = facts.evidence_record("row:1")
    reversed_repository.write_evidence_records([citation])
    participant = facts.entity("P1", citation=citation)
    reversed_repository.write_entities([participant], facts.ONTOLOGY_HASH)
    events = [
        facts.event(
            f"STAGE_{index}",
            facts.interval(index),
            citation=citation,
            participants=(participant,),
        )
        for index in range(6)
    ]
    reversed_repository.write_events(list(reversed(events)), facts.ONTOLOGY_HASH)
    reversed_repository.register_run(
        RunKey(
            dataset_version=facts.DATASET_VERSION,
            ontology_hash=facts.ONTOLOGY_HASH,
            rule_pack_version="1.0.0",
            engine_version="0.1.0",
            seed=0,
        )
    )
    reversed_repository.write_causal_edges(
        list(
            reversed(
                [facts.causal_edge(events[index], events[index + 1], run_id) for index in range(5)]
            )
        )
    )
    backward = InMemoryGraphProjection(repository=reversed_repository)

    assert forward.content_hash(run_id) == backward.content_hash(run_id)


def test_the_hash_is_identical_in_a_fresh_interpreter() -> None:
    """The hash must survive a process boundary, which `hash()` would not.

    Run in a subprocess with PYTHONHASHSEED unset, so a hash that depended on Python's
    randomised string hashing would differ here. Pinning the seed in this test instead
    would hide exactly the defect the test exists to find.
    """
    program = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, "src")
        sys.path.insert(0, ".")
        from tests.determinism.test_projection_hash_is_stable import _seeded_projection
        projection, run_id = _seeded_projection()
        print(projection.content_hash(run_id))
        """
    )
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[2]),
    )
    projection, run_id = _seeded_projection()
    assert completed.stdout.strip() == projection.content_hash(run_id), (
        "The projection hash differs between two interpreters. Something in the token "
        "stream depends on process state -- Python's randomised string hashing is the "
        "usual culprit -- and the step-6 determinism comparison would then report a defect "
        "on every rebuild that happened to run in a new process."
    )
