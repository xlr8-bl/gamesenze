"""scrape/soccerdata_jobs.py's frame-to-JSON conversion.

Reproduces a real failure seen live, after a ~20 minute FBref scrape: a
missing stat comes through pandas as float('nan'), json.dumps() happily
serializes that as a bare `NaN` token (valid Python, not valid JSON per
RFC 8259), and Postgres's json column correctly rejects it on insert —
"invalid input syntax for type json ... Token 'NaN' is invalid". No pandas
dependency needed here: _frame_to_records only requires reset_index() and
to_dict(orient=...), so a tiny fake stands in for a real DataFrame.
"""

from __future__ import annotations

import json
import math

from gamesenze.scrape.provenance import RawStore
from gamesenze.scrape.soccerdata_jobs import _frame_to_records, _json_safe
from tests.conftest import requires_pg


class _FakeFrame:
    """Duck-types the two DataFrame methods _frame_to_records actually uses."""

    def __init__(self, records: list[dict]) -> None:
        self._records = records
        self.reset_index_called = False

    def reset_index(self):
        self.reset_index_called = True
        return self

    def to_dict(self, orient: str):
        assert orient == "records"
        return self._records


def test_nan_becomes_none_not_an_invalid_json_token():
    frame = _FakeFrame([{"team": "Arsenal", "xg": float("nan"), "goals": 2}])

    records = _frame_to_records(frame)

    assert records == [{"team": "Arsenal", "xg": None, "goals": 2}]
    # The actual bug: json.dumps on the unfixed value produces the bare
    # token `NaN`, which json.loads accepts (Python's own leniency) but
    # Postgres's json column type does not. Asserting the string form
    # pins that the fix touched the encoding, not just the Python value.
    assert "NaN" not in json.dumps(records)


def test_positive_and_negative_infinity_also_become_none():
    frame = _FakeFrame([{"a": float("inf"), "b": float("-inf")}])

    records = _frame_to_records(frame)

    assert records == [{"a": None, "b": None}]


def test_a_normal_frame_is_unaffected():
    frame = _FakeFrame([{"team": "Arsenal", "xg": 1.8, "goals": 2}])

    records = _frame_to_records(frame)

    assert records == [{"team": "Arsenal", "xg": 1.8, "goals": 2}]
    assert frame.reset_index_called


def test_json_safe_recurses_into_nested_structures():
    value = {
        "outer": [{"inner": float("nan")}, {"inner": 3.0}],
        "plain": "text",
        "n": None,
    }

    assert _json_safe(value) == {
        "outer": [{"inner": None}, {"inner": 3.0}],
        "plain": "text",
        "n": None,
    }


def test_sanitized_records_always_round_trip_through_json():
    frame = _FakeFrame(
        [
            {"stat": float("nan")},
            {"stat": float("inf")},
            {"stat": float("-inf")},
            {"stat": 0.0},
        ]
    )

    records = _frame_to_records(frame)
    round_tripped = json.loads(json.dumps(records))

    assert round_tripped == records
    assert all(
        v is None or not (isinstance(v, float) and math.isnan(v))
        for r in round_tripped
        for v in r.values()
    )


@requires_pg
async def test_a_sanitized_fbref_style_payload_actually_stores(job_ctx):
    """The end of the pipeline the live failure hit: RawStore.store() writing
    into data_provenance.raw_response (a real jsonb column). Before this fix,
    the unsanitized payload's bare NaN token made Postgres reject the insert
    outright — "invalid input syntax for type json ... Token 'NaN' is
    invalid" — after a real ~20 minute scrape had already done the work.
    """
    frame = _FakeFrame([{"team": "Arsenal", "xg": float("nan"), "goals": 2}])
    payload = _frame_to_records(frame)

    digest = await RawStore(job_ctx.db).store(
        "fbref", "team_match_stats", payload, entity_ref="fbref:test"
    )

    assert digest
    stored = await job_ctx.db.fetchval(
        "select raw_response from data_provenance where content_hash = $1", digest
    )
    # asyncpg returns jsonb as text unless a codec is registered; decode to
    # compare values rather than assuming either representation.
    assert json.loads(stored) == payload
