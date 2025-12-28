# Zero@Campus Demo Runbook (Emergency Reset)

Use this guide if the demo environment becomes unstable or needs a clean slate before a presentation.

## 1. Fast Reset (Terminal)
Run these commands to clear state and restart services:

```bash
# Kill existing processes
pkill -f "uvicorn"
pkill -f "python3 -m http.server"

# Clear runtime evidence/backups (Optional - keep if you want history)
# rm -rf runtime/evidence/*.zip
# rm -rf runtime/backups/*.tar.gz

# Start Backend (Port 8095)
./run_backend.sh &

# Start Frontend (Port 8083)
./run_frontend.sh &
```

## 2. Check Health
Verify APIs are up:
```bash
curl -s http://127.0.0.1:8095/api/health | python3 -m json.tool
```

## 3. iPad Setup
1. Find Mac IP: `ipconfig getifaddr en0` (or en1)
2. Open on iPad Safari: `http://<MAC_IP>:8083/zero-campus.html?demo=1&safe=1`
   - `?demo=1`: Enables "Simulate Failure" buttons.
   - `?safe=1`: Disables destructive actions (prevents accidental full wipes).

## 4. "Evidence Moment" Flow
1. **Self-Heal**: Click "REAL Self-Heal" -> Watch "System Recovery" toast.
2. **Export**: Go to "Institutional Output" -> Click "GRI Report" -> PDF opens in new tab.
3. **Roadmap**: Go to "Generator Mode" -> "Add to Roadmap" -> "Success" toast.

## 5. Troubleshooting
- **Exports fail?** Check backend logs for ReportLab errors.
- **iPad won't connect?** Check Mac Firewall (Settings -> Network -> Firewall).
- **Stuck state?** Refresh page (Frontend is stateless, Backend holds state in memory). Restart Backend to wipe memory.
