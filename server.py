#!/usr/bin/env python3
"""
Kesh Monitoring v5 — Backend proxy with CSV logging.

Usage:
  python server.py                        # default port 8888
  MONITOR_PORT=9000 python server.py      # custom port

For static hosting (GitHub Pages / Cloudflare Pages):
  Just deploy index.html — it works standalone in browser mode.
  The server is optional and adds: real HTTP status codes, DNS checks,
  server-side latency measurement, and CSV logging.
"""

import concurrent.futures
import csv
import http.server
import json
import os
import socket
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import urllib.error
import urllib.request

PORT = int(os.environ.get("MONITOR_PORT", 8888))
REGION = os.environ.get("MONITOR_REGION", "MY-Penang")
LOG = "checks.csv"

# ── Traffic-light thresholds (must match index.html) ──
TH_GREEN = 100    # < 100ms  = fast (green)
TH_AMBER = 500    # 100-499  = elevated (amber)
TH_RED   = 3000   # 500-2999 = slow (red glow)
                   # 3000+    = critical (red blink)

TARGETS = [
    # ── Sentec ──
    {"id":"pms","label":"PMS","url":"https://pms.sentec.io","group":"Sentec","desc":"Property Management System"},
    {"id":"pos","label":"POS","url":"https://pos.sentec.io","group":"Sentec","desc":"Point of Sale"},
    {"id":"finance","label":"Finance","url":"https://finance.sentec.io","group":"Sentec","desc":"Financial system"},
    {"id":"ems","label":"EMS","url":"https://ems.sentec.io","group":"Sentec","desc":"Employee Management"},
    {"id":"ems-emp","label":"EMS Employees","url":"https://employees.ems.sentec.io","group":"Sentec","desc":"Employee portal"},
    # ── eInvoice Prod ──
    {"id":"einv-api","label":"e-Invoice API","url":"https://api.myinvois.hasil.gov.my","group":"eInvoice Prod","desc":"LHDN e-Invoice API"},
    {"id":"einv-portal","label":"e-Invoice Portal","url":"https://myinvois.hasil.gov.my","group":"eInvoice Prod","desc":"LHDN e-Invoice web portal"},
    {"id":"einv-id","label":"e-Invoice Identity","url":"https://identity.myinvois.hasil.gov.my","group":"eInvoice Prod","desc":"LHDN identity/auth"},
    # ── eInvoice Sandbox ──
    {"id":"einv-api-pp","label":"API (Sandbox)","url":"https://preprod-api.myinvois.hasil.gov.my","group":"eInvoice Sandbox","desc":"Pre-production API"},
    {"id":"einv-portal-pp","label":"Portal (Sandbox)","url":"https://preprod.myinvois.hasil.gov.my","group":"eInvoice Sandbox","desc":"Pre-production portal"},
    {"id":"einv-id-pp","label":"Identity (Sandbox)","url":"https://preprod-identity.myinvois.hasil.gov.my","group":"eInvoice Sandbox","desc":"Pre-production identity"},
    # ── Bookings / OTA ──
    {"id":"ota-booking","label":"Booking.com","url":"https://www.booking.com","group":"Bookings","desc":"Hotel booking platform"},
    {"id":"ota-agoda","label":"Agoda","url":"https://www.agoda.com","group":"Bookings","desc":"Hotel booking platform"},
    {"id":"ota-expedia","label":"Expedia","url":"https://www.expedia.com.my","group":"Bookings","desc":"Travel booking platform"},
    {"id":"ota-trip","label":"Trip.com","url":"https://www.trip.com","group":"Bookings","desc":"Travel booking platform"},
    {"id":"ota-airbnb","label":"Airbnb","url":"https://www.airbnb.com","group":"Bookings","desc":"Short-stay rental platform"},
    # ── Social & Reviews ──
    {"id":"soc-fb","label":"Facebook","url":"https://www.facebook.com","group":"Social","desc":"Social media platform"},
    {"id":"soc-ig","label":"Instagram","url":"https://www.instagram.com","group":"Social","desc":"Photo/video sharing"},
    {"id":"soc-tt","label":"TikTok","url":"https://www.tiktok.com","group":"Social","desc":"Short video platform"},
    {"id":"soc-wa","label":"WhatsApp Web","url":"https://web.whatsapp.com","group":"Social","desc":"Messaging web client"},
    {"id":"soc-ta","label":"TripAdvisor","url":"https://www.tripadvisor.com.my","group":"Social","desc":"Travel reviews"},
    # ── F&B Delivery ──
    {"id":"fnb-grab","label":"GrabFood","url":"https://food.grab.com","group":"F&B","desc":"Food delivery"},
    {"id":"fnb-panda","label":"foodpanda","url":"https://www.foodpanda.my","group":"F&B","desc":"Food delivery"},
    # ── MY ISPs ──
    {"id":"isp-tm","label":"TM / Unifi","url":"https://www.unifi.com.my","group":"Malaysia","desc":"Telekom Malaysia broadband"},
    {"id":"isp-maxis","label":"Maxis","url":"https://www.maxis.com.my","group":"Malaysia","desc":"Mobile & broadband"},
    {"id":"isp-digi","label":"CelcomDigi","url":"https://www.celcomdigi.com","group":"Malaysia","desc":"Mobile & broadband"},
    {"id":"isp-time","label":"TIME dotCom","url":"https://www.time.com.my","group":"Malaysia","desc":"Fibre broadband"},
    {"id":"isp-umob","label":"U Mobile","url":"https://www.u.com.my","group":"Malaysia","desc":"Mobile carrier"},
    # ── MY Services ──
    {"id":"my-lhdn","label":"LHDN (Hasil)","url":"https://www.hasil.gov.my","group":"Malaysia","desc":"Malaysian tax authority"},
    {"id":"my-gov","label":"MyGov","url":"https://www.malaysia.gov.my","group":"Malaysia","desc":"Government portal"},
    {"id":"my-bank","label":"Maybank","url":"https://www.maybank2u.com.my","group":"Malaysia","desc":"Online banking"},
    # ── Car Park (Whizcity) ──
    {"id":"cp-cloud","label":"Whizcity Cloud","url":"https://portal.whizcity.my","group":"Car Park","desc":"Whizcity cloud parking portal"},
    {"id":"cp-cloud-api","label":"Parking API","url":"https://portal.whizcity.my/discount/app/login","group":"Car Park","desc":"Cloud validation API endpoint"},
    # ── Global ──
    {"id":"gl-google","label":"Google","url":"https://www.google.com","group":"Global","desc":"Reference baseline"},
    {"id":"gl-cf","label":"Cloudflare","url":"https://www.cloudflare.com","group":"Global","desc":"CDN/DNS baseline"},
]

DNS_PROBES = ["pms.sentec.io", "google.com", "api.myinvois.hasil.gov.my", "portal.whizcity.my"]

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


def severity(ms, error):
    """Traffic-light severity matching the frontend."""
    if error:
        return "critical"
    if ms >= TH_RED:
        return "critical"
    if ms >= TH_AMBER:
        return "slow"
    if ms >= TH_GREEN:
        return "elevated"
    return "fast"


def ensure_log():
    if not Path(LOG).exists():
        with open(LOG, "w", newline="") as f:
            csv.writer(f).writerow([
                "timestamp_utc", "local_time", "id", "label", "url",
                "group", "status", "ms", "error", "region", "severity"
            ])


def log_row(target, result):
    sev = severity(result["response_time_ms"], result.get("error"))
    with open(LOG, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            target["id"], target["label"], target["url"],
            target.get("group", ""),
            result["status_code"], result["response_time_ms"],
            result.get("error") or "", REGION, sev,
        ])


def check_http(url, timeout=12):
    start = time.time()
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "KeshMonitor/5")
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx) as resp:
            resp.read(512)
            ms = round((time.time() - start) * 1000)
            return {"status_code": resp.status, "response_time_ms": ms, "error": None}
    except urllib.error.HTTPError as e:
        return {"status_code": e.code, "response_time_ms": round((time.time() - start) * 1000), "error": None}
    except urllib.error.URLError as e:
        return {"status_code": 0, "response_time_ms": round((time.time() - start) * 1000), "error": str(e.reason)[:120]}
    except Exception as e:
        return {"status_code": 0, "response_time_ms": round((time.time() - start) * 1000), "error": str(e)[:120]}


def check_dns(domain):
    start = time.time()
    try:
        socket.getaddrinfo(domain, 443)
        return {"resolve_ms": round((time.time() - start) * 1000), "error": None}
    except Exception as e:
        return {"resolve_ms": round((time.time() - start) * 1000), "error": str(e)[:120]}


def check_one(target):
    result = check_http(target["url"])
    result["timestamp"] = int(time.time() * 1000)
    result["region"] = REGION
    log_row(target, result)
    return target["id"], result


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/check-all":
            results = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                futures = {pool.submit(check_one, t): t for t in TARGETS}
                for f in concurrent.futures.as_completed(futures):
                    tid, r = f.result()
                    results[tid] = r
            dns = {d: check_dns(d) for d in DNS_PROBES}
            self._json({"checks": results, "dns": dns, "region": REGION})
            return

        if path == "/api/targets":
            self._json({"targets": TARGETS, "region": REGION})
            return

        if path == "/api/download-log":
            log_path = Path(LOG)
            if not log_path.exists():
                self.send_error(404)
                return
            data = log_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition",
                             f'attachment; filename="kesh-{datetime.now().strftime("%Y%m%d_%H%M")}.csv"')
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
            return

        # Serve static files (index.html etc.)
        super().do_GET()

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if "/api/" in str(args[0]):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    ensure_log()

    url = f"http://localhost:{PORT}"
    groups = list(dict.fromkeys(t["group"] for t in TARGETS))

    print(f"""
  ╔══════════════════════════════════════════╗
  ║   Kesh Monitoring v5 · Traffic Light Ed.  ║
  ║   Built by Kesh · Kesh · Penang             ║
  ╚══════════════════════════════════════════╝

  Dashboard:  {url}
  Region:     {REGION}
  Log file:   {LOG}
  Thresholds: <{TH_GREEN}ms green · {TH_GREEN}-{TH_AMBER-1}ms amber · {TH_AMBER}-{TH_RED-1}ms red · {TH_RED}ms+ critical
""")
    for g in groups:
        print(f"  [{g}]")
        for t in [x for x in TARGETS if x["group"] == g]:
            print(f"    {t['label']:22s} {t['url']}")

    print(f"\n  {len(TARGETS)} endpoints · parallel checks · Ctrl+C to stop\n")

    try:
        with http.server.HTTPServer(("0.0.0.0", PORT), Handler) as server:
            server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
