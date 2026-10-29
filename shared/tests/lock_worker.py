"""Child process for test_heavy_lock: takes the lock the way another project would."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ngm_shared.heavy_lock import HeavyLock  # noqa: E402

mode, path = sys.argv[1], Path(sys.argv[2])

if mode == "once":      # every child tries at the same moment; exactly one may win
    start = float(sys.argv[3])
    time.sleep(max(0.0, start - time.time() - 0.05))
    while time.time() < start:
        pass
    if time.time() > start + 0.5:
        print("late", flush=True)
        sys.exit(0)
    lock = HeavyLock(path, f"child-{os.getpid()}")
    won = lock.try_acquire("gpu")
    print(int(won), flush=True)
    time.sleep(1.5)     # late arrivals must still find it taken
    if won:
        lock.release()
elif mode == "stress":  # many rounds; a second marker file inside the lock = two holders at once
    marker, rounds = Path(sys.argv[3]), int(sys.argv[4])
    lock = HeavyLock(path, "stress")
    overlaps = 0
    for _ in range(rounds):
        lock.acquire(60, "blender", poll_s=0.002)
        try:
            fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            overlaps += 1
        else:
            os.close(fd)
            time.sleep(0.002)
            os.remove(marker)
        lock.release()
    print(overlaps, flush=True)
elif mode == "hold":    # holds the lock until killed
    HeavyLock(path, "klapka").acquire(10, "blender", caller="scena-12")
    print("held", flush=True)
    time.sleep(120)
