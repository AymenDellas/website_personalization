"""
proxy_validator.py
Tests proxies concurrently, builds a thread-safe ProxyPool.
Auto-refills when pool drops low.
"""

import queue
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from logger import log

TEST_URL = "https://httpbin.org/ip"
TIMEOUT = 8          # seconds
WORKERS = 40         # concurrent test threads
REFILL_THRESHOLD = 3 # refill when pool drops below this


def _test_proxy(proxy: dict) -> dict | None:
    """
    Returns proxy dict if working, None if dead.
    """
    ip, port = proxy["ip"], proxy["port"]
    proxy_str = f"http://{ip}:{port}"
    try:
        resp = requests.get(
            TEST_URL,
            proxies={"http": proxy_str, "https": proxy_str},
            timeout=TIMEOUT,
            verify=False   # Many free proxies have bad SSL certs
        )
        if resp.status_code == 200 and "origin" in resp.json():
            return proxy
    except Exception:
        pass
    return None


def validate(raw_proxies: list[dict], stop_event: threading.Event = None) -> list[dict]:
    """
    Tests all proxies concurrently.
    Returns list of working proxies.
    """
    log(f"[Validator] Testing {len(raw_proxies)} proxies with {WORKERS} workers...")
    working = []

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(_test_proxy, p): p for p in raw_proxies}
        for future in as_completed(futures):
            if stop_event and stop_event.is_set():
                break
            result = future.result()
            if result:
                working.append(result)

    log(f"[Validator] {len(working)} working proxies found out of {len(raw_proxies)} tested.")
    return working


class ProxyPool:
    """
    Thread-safe proxy pool backed by a queue.Queue.
    Auto-refills when pool drops below REFILL_THRESHOLD.
    """

    def __init__(self, working_proxies: list[dict]):
        self._q = queue.Queue()
        self._lock = threading.Lock()
        self._refilling = False
        for p in working_proxies:
            self._q.put(p)
        log(f"[ProxyPool] Initialized with {self._q.qsize()} proxies.")

    def get(self) -> dict | None:
        """Get next working proxy. Returns None if pool is exhausted."""
        # Trigger background refill if running low
        if self._q.qsize() < REFILL_THRESHOLD and not self._refilling:
            self._start_refill()

        try:
            return self._q.get_nowait()
        except queue.Empty:
            log("[ProxyPool] Pool empty — waiting for refill...")
            # Block up to 60s for refill
            try:
                return self._q.get(timeout=60)
            except queue.Empty:
                log("[ProxyPool] WARNING: Refill timed out, no proxies available.")
                return None

    def put_back(self, proxy: dict):
        """Return a proxy to the pool (e.g. after a successful use)."""
        self._q.put(proxy)

    def mark_dead(self, proxy: dict):
        """Mark proxy as dead — don't return it to pool."""
        log(f"[ProxyPool] Marked dead: {proxy['ip']}:{proxy['port']} "
            f"(pool size: {self._q.qsize()})")

    def size(self) -> int:
        return self._q.qsize()

    def _start_refill(self):
        with self._lock:
            if self._refilling:
                return
            self._refilling = True

        log("[ProxyPool] Pool running low — triggering background refill...")
        t = threading.Thread(target=self._refill_worker, daemon=True)
        t.start()

    def _refill_worker(self):
        try:
            from proxy_harvester import harvest
            raw = harvest()
            working = validate(raw)
            for p in working:
                self._q.put(p)
            log(f"[ProxyPool] Refill complete — added {len(working)} proxies. "
                f"Pool size: {self._q.qsize()}")
        except Exception as e:
            log(f"[ProxyPool] Refill FAILED: {e}")
        finally:
            with self._lock:
                self._refilling = False


if __name__ == "__main__":
    from proxy_harvester import harvest
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    raw = harvest()
    working = validate(raw)
    print(f"\n✅ {len(working)} working proxies:")
    for p in working[:10]:
        print(f"  {p['ip']}:{p['port']}")
