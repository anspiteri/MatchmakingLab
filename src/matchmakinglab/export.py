"""Write a run's per-tick data to a file, with the format chosen by extension.

`.csv` gets a header row and one row per tick, for anything that opens in a
spreadsheet. `.jsonl` gets one JSON object per line, for anything that would
rather not parse a fixed-width file or wants the values typed rather than
textual. The suffix is the only thing that decides, so there is no second flag
to keep in step with the first.
"""

import csv
import json
from pathlib import Path
from types import TracebackType
from typing import IO, Self

from matchmakinglab.core.snapshot import SimSnapshot

#: The exported columns, in order. The snapshot's scalar facts only.
#:
#: `queue` goes out as its length rather than as the usernames, and
#: `event_lines` and `leaderboard` are left out entirely: all three are
#: per-tick lists whose size says nothing about the run, and a hundred leaderboard
#: rows a tick would bury the numbers they are meant to sit beside.
FIELDS = (
    "tick",
    "population_size",
    "queue_size",
    "active_matches",
    "finished_matches",
    "sim_seconds",
    "request_rate",
    "avg_wait",
    "avg_match_len",
    "favourite_win_rate",
    "rating_accuracy",
    "rating_spread",
    "true_skill_spread",
)

SUPPORTED_SUFFIXES = (".csv", ".jsonl")


def snapshot_row(snapshot: SimSnapshot) -> dict[str, float | int]:
    """One snapshot as a flat mapping of the exported fields.

    Read off the snapshot by name rather than by position, so a field added to
    `FIELDS` cannot silently pick up a neighbour's value.
    """
    values: dict[str, float | int] = {}
    for field in FIELDS:
        if field == "queue_size":
            values[field] = len(snapshot.queue)
        else:
            values[field] = getattr(snapshot, field)
    return values


class SnapshotWriter:
    """Append one row per tick to an open file. Use as a context manager.

    Opening in the constructor rather than on first write means a bad path or an
    unknown extension is reported before the run starts, not after an hour of
    simulation that is then thrown away.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        suffix = self.path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            supported = ", ".join(SUPPORTED_SUFFIXES)
            raise ValueError(
                f"Cannot export to '{self.path}': unknown extension "
                f"'{self.path.suffix}'. Supported: {supported}."
            )
        self._format = suffix
        self._handle: IO[str] | None = None

    def __enter__(self) -> Self:
        self._handle = self.path.open("w", newline="", encoding="utf-8")
        if self._format == ".csv":
            # The header is written here rather than on the first snapshot, so
            # a run that produced no rows still says what the columns are.
            writer = csv.writer(self._handle)
            writer.writerow(FIELDS)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def write(self, snapshot: SimSnapshot) -> None:
        """Record one tick. Called once per `step()`."""
        if self._handle is None:
            raise RuntimeError(
                f"{type(self).__name__} is closed; use it as a context manager"
            )
        row = snapshot_row(snapshot)
        if self._format == ".csv":
            csv.writer(self._handle).writerow([row[field] for field in FIELDS])
        else:
            # One compact object per line. `default=str` for a value that is not
            # JSON-native, so an unexpected type costs a readable string rather
            # than the whole run's output.
            self._handle.write(json.dumps(row, default=str) + "\n")

    def flush(self) -> None:
        """Push buffered rows out, so a long run can be watched while it goes."""
        if self._handle is not None:
            self._handle.flush()
