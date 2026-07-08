#!/usr/bin/env python3
"""
Kesh Monitoring — GitHub Actions check runner.
Checks all endpoints in parallel, appends results to logs/checks.csv.
Zero dependencies — uses only Python stdlib.
"""

import concurrent.futures
import csv
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REGION = "GitHub-Actions"
LOG = "logs/checks.csv"

TH_GREEN = 100
TH_AMBER = 500
TH_RED = 3000

TARGETS = [
    # ── Sentec ──
    {"id": "pms", "label": "PMS", "url": "https://pms.sentec.io", "group": "Sentec"},
    {"id": "pos", "label": "POS", "url": "https://pos.sentec.io", "group": "Sentec"},
    {"id": "finance", "label": "Finance", "url": "https://finance.sentec.io", "group": "Sentec"},
    {"id": "ems", "label": "EMS", "url": "https://ems.sentec.io", "group": "Sentec"},
    {"id": "ems-emp", "label": "EMS Employees", "url": "https://employees.ems.sentec.io", "group": "Sentec"},
    # ── Sentec Deep Health ──
    {"id": "pms-health", "label": "PMS Web Health", "url": "https://apse1.pms.sentec.io/health.txt", "group": "Sentec", "health": "txt"},
    {"id": "pms-api-health", "label": "PMS API Health", "url": "https://apse1.api.pms.sentec.io/health/", "group": "Sentec", "health": "json"},
    # ── eInvoice Prod ──
    {"id": "einv-api", "label": "e-Invoice API", "url": "https://api.myinvois.hasil.gov.my", "group": "eInvoice Prod"},
    {"id": "einv-portal", "label": "e-Invoice Portal", "url": "https://myinvois.hasil.gov.my", "group": "eInvoice Prod"},
    {"id": "einv-id", "label": "e-Invoice Identity", "url": "https://identity.myinvois.hasil.gov.my", "group": "eInvoice Prod"},
    # ── eInvoice Sandbox ──
    {"id": "einv-api-pp", "label": "API (Sandbox)", "url": "https://preprod-api.myinvois.hasil.gov.my", "group": "eInvoice Sandbox"},
    {"id": "einv-portal-pp", "label": "Portal (Sandbox)", "url": "https://preprod.myinvois.hasil.gov.my", "group": "eInvoice Sandbox"},
    {"id": "einv-id-pp", "label": "Identity (Sandbox)", "url": "https://preprod-identity.myinvois.hasil.gov.my", "group": "eInvoice Sandbox"},
    # ── Car Park (Whizcity) ──
    {"id": "cp-cloud", "label": "Whizcity Cloud", "url": "https://portal.whizcity.my", "group": "Car Park"},
    {"id": "cp-cloud-api", "label": "Parking API", "url": "https://portal.whizcity.my/discount/app/login", "group": "Car Park"},
    # ── Bookings / OTA ──
    {"id": "ota-booking", "label": "Booking.com", "url": "https://www.booking.com", "group": "Bookings"},
    {"id": "ota-agoda", "label": "Agoda", "url": "https://www.agoda.com", "group": "Bookings"},
    {"id": "ota-expedia", "label": "Expedia", "url": "https://www.expedia.com.my", "group": "Bookings"},
    {"id": "ota-trip", "label": "Trip.com", "url": "https://www.trip.com", "group": "Bookings"},
    {"id": "ota-airbnb", "label": "Airbnb", "url": "https://www.airbnb.com", "group": "Bookings"},
    # ── Social & Reviews ──
    {"id": "soc-fb", "label": "Facebook", "url": "https://www.facebook.com", "group": "Social"},
    {"id": "soc-ig", "label": "Instagram", "url": "https://www.instagram.com", "group": "Social"},
    {"id": "soc-tt", "label": "TikTok", "url": "https://www.tiktok.com", "group": "Social"},
    {"id": "soc-wa", "label": "WhatsApp Web", "url": "https://web.whatsapp.com", "group": "Social"},
    {"id": "soc-ta", "label": "TripAdvisor", "url": "https://www.tripadvisor.com.my", "group": "Social"},
    # ── F&B Delivery ──
    {"id": "fnb-grab", "label": "GrabFood", "url": "https://food.grab.com", "group": "F&B"},
    {"id": "fnb-panda", "label": "foodpanda", "url": "https://www.foodpanda.my", "group": "F&B"},
    # ── MY ISPs ──
    {"id": "isp-tm", "label": "TM / Unifi", "url": "https://www.unifi.com.my", "group": "Malaysia"},
    {"id": "isp-maxis", "label": "Maxis", "url": "https://www.maxis.com.my", "group": "Malaysia"},
    {"id": "isp-digi", "label": "CelcomDigi", "url": "https://www.celcomdigi.com", "group": "Malaysia"},
    {"id": "isp-time", "label": "TIME dotCom", "url": "https://www.time.com.my", "group": "Malaysia"},
    {"id": "isp-umob", "label": "U Mobile", "url": "https://www.u.com.my", "group": "Malaysia"},
    # ── MY Services ──
    {"id": "my-lhdn", "label": "LHDN (Hasil)", "url": "https://www.hasil.gov.my", "group": "Malaysia"},
    {"id": "my-gov", "label": "MyGov", "url": "https://www.malaysia.gov.my", "group": "Malaysia"},
    {"id": "my-bank", "label": "Maybank", "url": "https://www.maybank2u.com.my", "group": "Malaysia"},
    # ── Global ──
    {"id": "gl-google", "label": "Google", "url": "https://www.google.com", "group": "Global"},
    {"id": "gl-cf", "label": "Cloudflare", "url": "https://www.cloudflare.com", "group": "Global"},
]

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


def severity(ms, error):
    if error:
        return "critical"
    if ms >= TH_RED:
        return "critical"
    if ms >= TH_AMBER:
        return "slow"
    if ms >= TH_GREEN:
        return "elevated"
    return "fast"


def check_http(url, timeout=12):
    start = time.time()
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "KeshMonitor/5-GHA")
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


def check_health(target):
    """Extended health check — parses response body for subsystem status."""
    health_type = target.get("health")
    if not health_type:
        return check_http(target["url"])

    url = target["url"]
    start = time.time()
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "KeshMonitor/5-GHA")
        with urllib.request.urlopen(req, timeout=12, context=ssl_ctx) as resp:
            body = resp.read(4096).decode("utf-8", errors="replace")
            ms = round((time.time() - start) * 1000)
            result = {"status_code": resp.status, "response_time_ms": ms, "error": None}

            if health_type == "txt":
                is_ok = "ok" in body.strip().lower()
                result["health_detail"] = {"web": "\u2705" if is_ok else "\u274c"}
                if not is_ok:
                    result["error"] = f"health.txt returned: {body.strip()[:60]}"

            elif health_type == "json":
                try:
                    data = json.loads(body)
                    detail = {}
                    all_ok = True
                    for key, val in data.items():
                        ok = val.strip() == "\u2705" if isinstance(val, str) else bool(val)
                        detail[key] = "\u2705" if ok else "\u274c"
                        if not ok:
                            all_ok = False
                    result["health_detail"] = detail
                    if not all_ok:
                        failed = [k for k, v in detail.items() if v == "\u274c"]
                        result["error"] = f"Degraded: {', '.join(failed)}"
                except (json.JSONDecodeError, ValueError):
                    result["health_detail"] = {"parse": "\u274c"}
                    result["error"] = f"Invalid health JSON: {body.strip()[:60]}"

            return result
    except urllib.error.HTTPError as e:
        return {"status_code": e.code, "response_time_ms": round((time.time() - start) * 1000), "error": None}
    except urllib.error.URLError as e:
        return {"status_code": 0, "response_time_ms": round((time.time() - start) * 1000), "error": str(e.reason)[:120]}
    except Exception as e:
        return {"status_code": 0, "response_time_ms": round((time.time() - start) * 1000), "error": str(e)[:120]}


def main():
    # Ensure logs directory and CSV header exist
    Path("logs").mkdir(exist_ok=True)
    log_path = Path(LOG)
    write_header = not log_path.exists() or log_path.stat().st_size == 0

    now_utc = datetime.now(timezone.utc)
    ts = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Run all checks in parallel (using check_health for deep probes)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(check_health, t): t for t in TARGETS}
        for f in concurrent.futures.as_completed(futures):
            t = futures[f]
            r = f.result()
            sev = severity(r["response_time_ms"], r.get("error"))
            hd = r.get("health_detail")
            results.append({
                "timestamp_utc": ts,
                "id": t["id"],
                "label": t["label"],
                "url": t["url"],
                "group": t["group"],
                "status": r["status_code"],
                "ms": r["response_time_ms"],
                "error": r.get("error") or "",
                "region": REGION,
                "severity": sev,
                "health_detail": json.dumps(hd) if hd else "",
            })

    # Append to CSV
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["timestamp_utc", "id", "label", "url", "group",
                         "status", "ms", "error", "region", "severity",
                         "health_detail"])
        for r in results:
            w.writerow([r["timestamp_utc"], r["id"], r["label"], r["url"],
                         r["group"], r["status"], r["ms"], r["error"],
                         r["region"], r["severity"], r["health_detail"]])

    # Print summary
    ok = sum(1 for r in results if r["severity"] == "fast")
    warn = sum(1 for r in results if r["severity"] in ("elevated", "slow"))
    bad = sum(1 for r in results if r["severity"] == "critical")
    print(f"  {ts}  ✅ {ok}  ⚠️ {warn}  ❌ {bad}  ({len(results)} endpoints)")

    # Trim CSV if it gets too large (keep last 50,000 lines ≈ ~7 days at 30-min intervals)
    MAX_LINES = 50_000
    lines = log_path.read_text().splitlines()
    if len(lines) > MAX_LINES:
        header = lines[0]
        trimmed = [header] + lines[-(MAX_LINES - 1):]
        log_path.write_text("\n".join(trimmed) + "\n")
        print(f"  Trimmed CSV: {len(lines)} → {len(trimmed)} lines")


if __name__ == "__main__":
    main()
