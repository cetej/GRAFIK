"""Kdo čeká déle, jde první: rychlá fronta Engine nesmí předbíhat Blender jiného procesu (1. 11. čekal 20 minut a vzdal to)."""
from __future__ import annotations

import os
import threading
import time

import psutil

from ngm_shared.heavy_lock import HeavyLock


def _lines(path, n):
    return [HeavyLock(path, f"owner-{i}") for i in range(n)]


def test_busy_queue_cannot_starve_a_waiter(tmp_path):
    path = tmp_path / "lock"
    busy, waiter = _lines(path, 2)
    stop = threading.Event()
    rounds = [0]

    def queue():   # jako fronta Engine: hned po uvolnění bere zámek znovu
        while not stop.is_set():
            busy.acquire(10, poll_s=0.01)
            rounds[0] += 1
            time.sleep(0.05)
            busy.release()

    t = threading.Thread(target=queue)
    t.start()
    time.sleep(0.2)
    before = rounds[0]
    waiter.acquire(5, poll_s=0.5)
    overtook = rounds[0] - before
    waiter.release()
    stop.set()
    t.join()
    assert overtook <= 1   # nejvýš kolo, které už běželo, a žádné další


def test_waiters_go_in_order_of_arrival(tmp_path):
    path = tmp_path / "lock"
    first, second, third = _lines(path, 3)
    assert first.try_acquire()
    order = []

    def take(lock):
        lock.acquire(10, poll_s=0.01)
        order.append(lock.owner)
        time.sleep(0.05)
        lock.release()

    threads = [threading.Thread(target=take, args=(lock,)) for lock in (second, third)]
    threads[0].start()
    time.sleep(0.1)
    threads[1].start()
    time.sleep(0.1)
    first.release()
    for t in threads:
        t.join()
    assert order == ["owner-1", "owner-2"]


def test_ticket_of_dead_process_and_old_ticket_do_not_block(tmp_path):
    path = tmp_path / "lock"
    queue = path.with_name(path.name + ".waiting")
    queue.mkdir()
    dead = next(p for p in range(90000, 99000) if not psutil.pid_exists(p))
    (queue / f"1-{dead}-1").touch()
    old = queue / f"2-{os.getpid()}-999"
    old.touch()
    os.utime(old, (time.time() - 600, time.time() - 600))
    lock = HeavyLock(path, "ja")
    start = time.monotonic()
    lock.acquire(1, poll_s=0.01)
    assert time.monotonic() - start < 0.5
    lock.release()
    assert not list(queue.iterdir())


def test_own_lock_needs_no_queue(tmp_path):
    path = tmp_path / "lock"
    lock, other = _lines(path, 2)
    assert lock.try_acquire()
    t = threading.Thread(target=lambda: other.acquire(2, poll_s=0.01) or other.release())
    t.start()
    time.sleep(0.1)
    lock.acquire(0.5, poll_s=0.01)   # držitel se nesmí zablokovat o čekajícího za sebou
    lock.release()
    t.join()
