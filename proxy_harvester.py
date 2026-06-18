"""
proxy_harvester.py
Scrapes raw proxy lists from multiple free sources.
Returns deduplicated list of {"ip": str, "port": str, "https": bool}
"""

import requests
import re
from logger import log

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def _harvest_free_proxy_list() -> list[dict]:
    """Scrapes free-proxy-list.net"""
    proxies = []
    try:
        resp = requests.get("https://free-proxy-list.net/", headers=HEADERS, timeout=15)
        # Parse the textarea block which contains the proxy list
        match = re.search(r'<textarea[^>]*>(.*?)</textarea>', resp.text, re.DOTALL)
        if match:
            raw = match.group(1)
            for line in raw.strip().split('\n'):
                line = line.strip()
                if re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', line):
                    ip, port = line.split(':')
                    proxies.append({"ip": ip, "port": port, "https": True})
        # Also parse the old table format as fallback
        if not proxies:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'lxml')
            rows = soup.select('table tbody tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 7:
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    https = cols[6].text.strip().lower() == 'yes'
                    if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip) and port.isdigit():
                        proxies.append({"ip": ip, "port": port, "https": https})
        log(f"[Harvester] free-proxy-list.net -> {len(proxies)} proxies")
    except Exception as e:
        log(f"[Harvester] free-proxy-list.net FAILED: {e}")
    return proxies


def _harvest_ssl_proxies() -> list[dict]:
    """Scrapes sslproxies.org (HTTPS only)"""
    proxies = []
    try:
        from bs4 import BeautifulSoup
        resp = requests.get("https://www.sslproxies.org/", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, 'lxml')
        rows = soup.select('table tbody tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 2:
                ip = cols[0].text.strip()
                port = cols[1].text.strip()
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip) and port.isdigit():
                    proxies.append({"ip": ip, "port": port, "https": True})
        log(f"[Harvester] sslproxies.org -> {len(proxies)} proxies")
    except Exception as e:
        log(f"[Harvester] sslproxies.org FAILED: {e}")
    return proxies


def _harvest_proxy_list_download() -> list[dict]:
    """Plain-text API — no parsing needed"""
    proxies = []
    try:
        resp = requests.get(
            "https://www.proxy-list.download/api/v1/get?type=https",
            headers=HEADERS,
            timeout=15
        )
        for line in resp.text.strip().split('\n'):
            line = line.strip()
            if re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', line):
                ip, port = line.split(':')
                proxies.append({"ip": ip, "port": port, "https": True})
        log(f"[Harvester] proxy-list.download -> {len(proxies)} proxies")
    except Exception as e:
        log(f"[Harvester] proxy-list.download FAILED: {e}")
    return proxies


def _harvest_proxyscrape() -> list[dict]:
    """ProxyScrape free API"""
    proxies = []
    try:
        resp = requests.get(
            "https://api.proxyscrape.com/v3/free-proxy-list/get"
            "?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=yes&anonymity=all",
            headers=HEADERS,
            timeout=15
        )
        for line in resp.text.strip().split('\n'):
            line = line.strip()
            if re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', line):
                ip, port = line.split(':')
                proxies.append({"ip": ip, "port": port, "https": True})
        log(f"[Harvester] proxyscrape.com -> {len(proxies)} proxies")
    except Exception as e:
        log(f"[Harvester] proxyscrape.com FAILED: {e}")
    return proxies


def harvest() -> list[dict]:
    """
    Harvest proxies from all sources, deduplicate, and return.
    """
    log("[Harvester] Starting proxy harvest from all sources...")
    all_proxies = []

    all_proxies.extend(_harvest_free_proxy_list())
    all_proxies.extend(_harvest_ssl_proxies())
    all_proxies.extend(_harvest_proxy_list_download())
    all_proxies.extend(_harvest_proxyscrape())

    # Deduplicate by ip:port
    seen = set()
    unique = []
    for p in all_proxies:
        key = f"{p['ip']}:{p['port']}"
        if key not in seen:
            seen.add(key)
            unique.append(p)

    log(f"[Harvester] Total unique proxies harvested: {len(unique)}")
    return unique


if __name__ == "__main__":
    results = harvest()
    print(f"Harvested {len(results)} proxies")
    for p in results[:10]:
        print(p)
