# 📡 Kesh Monitoring

**Real-time uptime & latency status page with traffic-light alerts.**
One HTML file. No build step. Deploy to GitHub Pages in 60 seconds.

![Kesh Monitoring](https://img.shields.io/badge/version-5.0-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Static Hosting](https://img.shields.io/badge/hosting-GitHub%20Pages%20%7C%20Cloudflare-orange)

---

## What is this?

A self-hosted status page that monitors 34 endpoints across multiple service groups — from your own internal systems to third-party platforms. Think Uptime Robot or Pulsetic, but it's a single HTML file you own and control.

Built for the team at **Neo Penang** to keep an eye on hotel tech (PMS, POS, Finance, EMS), Malaysia's e-Invoice system (LHDN MyInvois), OTA platforms, social media, ISPs, and more — all from one dashboard.

### Who is this for?

- **IT teams** who want a quick status page without paying for SaaS
- **Hotel / hospitality ops** monitoring PMS, channel managers, and OTAs
- **Malaysian businesses** tracking e-Invoice (MyInvois) uptime
- **Anyone** who wants a clean, self-hosted uptime dashboard

---

## Features

### Traffic-Light Alert System
Latency numbers, status dots, and card borders dynamically change color based on response time:

| Response Time | Color | Visual Effect | Meaning |
|---|---|---|---|
| < 100 ms | 🟢 Green | Steady | Working normally |
| 100–499 ms | 🟡 Amber | Pulsing | Slower than usual |
| 500–2999 ms | 🔴 Red | Glowing | Experiencing delays |
| 3000 ms+ / Error | 🔴 Red | Blinking + card glow | Needs attention |

### Clear for Everyone
- **Non-technical?** Every endpoint shows plain English: *"Working normally"*, *"Slower than usual"*, *"Not responding"*
- **Technical?** Toggle to see HTTP status codes, full URLs, p95 latency, and sparkline charts
- **Simple Mode** in Settings hides all the nerdy stuff

### Core vs External
- **CORE** (Sentec & eInvoice) — drives the status banner, uptime %, and sound alerts
- **EXTERNAL** (Booking.com, Facebook, ISPs, etc.) — monitored for reference, won't trigger alarms

### Everything Else
- 🌗 Dark / light theme (auto-detects system preference)
- 🔊 Sound alerts when a core service goes down (toggle in settings)
- 📊 Per-endpoint sparkline charts with threshold lines
- 📋 CSV export of all collected data
- 📱 Fully responsive — works on phone, tablet, desktop
- ⏱️ Auto-checks every 30 seconds with countdown timer
- 🗂️ Group tabs with health indicators
- 💾 History persists in localStorage (survives refresh)
- 🚨 A very important-looking Incident Response button (try it)

---

## Quick Start

### Option 1: Static Hosting (GitHub Pages / Cloudflare Pages)

Just the HTML file. No server needed.

1. Fork this repo (or create a new one and drop in `index.html`)
2. Go to **Settings → Pages → Source: main branch**
3. Your status page is live at `https://yourusername.github.io/kesh-monitoring/`

> **Browser mode:** Checks are done client-side using `fetch` with `no-cors`. You get latency data but not HTTP status codes. Some sites with strict security (e.g. Maybank) will always show as down — that's their CORS policy, not an actual outage.

### Option 2: With Server (Full Features)

The Python server adds real HTTP status codes, DNS resolution checks, and server-side CSV logging.

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/kesh-monitoring.git
cd kesh-monitoring

# Run the server (Python 3.6+, no dependencies)
python server.py

# Open http://localhost:8888
```

Optional environment variables:

```bash
MONITOR_PORT=9000 python server.py        # custom port
MONITOR_REGION=MY-KL python server.py     # custom region label
```

---

## Customizing Endpoints

### Static hosting (index.html only)

Edit the `TARGETS_FALLBACK` array inside `index.html`:

```javascript
const TARGETS_FALLBACK = [
  {
    id: "my-app",                        // unique ID
    label: "My App",                     // display name
    url: "https://app.example.com",      // URL to check
    group: "My Services",                // group tab
    desc: "Main customer-facing app"     // human-readable description
  },
  // ... add more
];
```

### With server

Edit the `TARGETS` list in `server.py` — same structure. The frontend auto-loads targets from the server API when available.

### Changing which groups are "critical"

Edit the `CRITICAL_GROUPS` array in `index.html`:

```javascript
// Only these groups affect the hero banner + sound alerts
const CRITICAL_GROUPS = ['Sentec', 'eInvoice Prod', 'eInvoice Sandbox'];
```

### Adjusting thresholds

```javascript
const TH_GREEN = 100;   // under this = green
const TH_AMBER = 500;   // 100-499 = amber
const TH_RED   = 3000;  // 500-2999 = red glow, 3000+ = red blink
```

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  index.html (single file, zero dependencies)    │
│                                                 │
│  ┌─────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Browser │  │ Traffic  │  │ localStorage  │  │
│  │  fetch  │→ │  Light   │→ │   History     │  │
│  │ checks  │  │  Engine  │  │  + CSV Export  │  │
│  └─────────┘  └──────────┘  └───────────────┘  │
│       ↑                                         │
│  Falls back to browser if server unavailable    │
├─────────────────────────────────────────────────┤
│  server.py (optional, Python 3.6+)              │
│                                                 │
│  ┌─────────┐  ┌──────────┐  ┌───────────────┐  │
│  │  HTTP   │  │   DNS    │  │  CSV Logger   │  │
│  │ checks  │  │  probes  │  │  (checks.csv) │  │
│  │ (real)  │  │          │  │               │  │
│  └─────────┘  └──────────┘  └───────────────┘  │
└─────────────────────────────────────────────────┘
```

- **Browser mode**: `fetch` with `no-cors` → measures round-trip latency. No HTTP codes (opaque response). Works on any static host.
- **Server mode**: Python `urllib` → real HTTP status codes, DNS resolution times, CSV logging. Parallel checks with 12 threads.

---

## File Structure

```
kesh-monitoring/
├── index.html      ← The entire dashboard (drop this on GitHub Pages)
├── server.py       ← Optional backend for richer data
├── checks.csv      ← Auto-generated when using server.py
└── README.md
```

Yes, it's really just one HTML file. CSS, JS, all inline. No npm, no webpack, no React, no build step.

---

## FAQ

**Q: History resets when I clear my browser?**
Yes — on static hosting, history lives in `localStorage`. It survives refreshes and browser restarts, but clearing site data wipes it. Use the CSV export button to save snapshots. Each device has its own history.

**Q: Why does Maybank / some bank always show as "down"?**
Banks use aggressive bot protection that blocks browser-based `fetch` requests entirely. This is normal in browser mode. Run `server.py` locally for accurate checks on these endpoints.

**Q: Can I monitor my own APIs?**
Absolutely. Add them to `TARGETS_FALLBACK` in `index.html` (or `TARGETS` in `server.py`). Any URL that responds to a GET request works.

**Q: What's the Incident Response button do?**
Try it and find out. 🍛

---

## Tech Stack

- **Frontend**: Vanilla HTML/CSS/JS — zero dependencies
- **Backend**: Python 3 standard library — zero pip installs
- **Hosting**: GitHub Pages, Cloudflare Pages, Netlify, or any static host
- **Storage**: `localStorage` (browser) / CSV (server)

---

## License

MIT — do whatever you want with it.

---

<p align="center">
  <b>Kesh Monitoring v5</b> · Built by Kesh · Penang 🇲🇾
</p>
