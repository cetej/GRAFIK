"""One process of test_knihovna's concurrency test: adds 1 to a card's count N times through update()."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ngm_shared import knihovna  # noqa: E402

base, rounds = Path(sys.argv[1]), int(sys.argv[2])
for _ in range(rounds):
    knihovna.update("prop", "pocitadlo", lambda c: {**c, "count": int(c.get("count") or 0) + 1}, base=base)
