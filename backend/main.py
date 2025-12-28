from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import time
import random
import datetime
import os
import tarfile
import requests
import glob

app = FastAPI()

# Config
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://127.0.0.1:5678")
BACKUP_DIR = "runtime/backups"

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Models ---

class SystemStatus(BaseModel):
    system_state: str  # OK, DEGRADED, HEALING
    brain: str
    agents: str
    backup: str
    cache: str
    last_incident: Optional[str] = None
    latency_ms: Optional[int] = None
    updated_at: Optional[str] = None
    backend_version: Optional[str] = None

class Workflow(BaseModel):
    name: str
    status: str
    last_run: str
    next_run: str

class OrchestratorStatus(BaseModel):
    ok: bool
    workflows: List[Workflow]
    queue: dict
    webhooks_last_ping: str

class Incident(BaseModel):
    ts: str
    type: str
    action: str
    result: str
    severity: str = "LOW"
    duration_ms: Optional[int] = None

class IncidentLog(BaseModel):
    incidents: List[Incident]

class BrainIntent(BaseModel):
    intent: str
    recommended_tab: str

class BackupResponse(BaseModel):
    ok: bool
    file: str
    size_bytes: int
    ts: str

class BackupStatus(BaseModel):
    last_ok_ts: Optional[str] = None
    last_file: Optional[str] = None
    size_bytes: Optional[int] = None
    age_seconds: Optional[int] = None

# --- State ---

state = {
    "system_status": "OK",
    "last_incident": None,
    "workflows": [
        {"name": "Incident Agent", "status": "Running", "last_run": "2m ago", "next_run": "in 3m"},
        {"name": "Evidence Agent", "status": "Running", "last_run": "5m ago", "next_run": "in 10m"},
        {"name": "Backup Agent", "status": "Idle", "last_run": "1h ago", "next_run": "in 5h"},
        {"name": "Forecast Refresh", "status": "Running", "last_run": "10m ago", "next_run": "in 50m"}
    ],
    "incidents": [],
    "last_backup": {
        "ts": None,
        "file": None,
        "size": 0
    }
}

# --- Catalog & Scope Logic (v0.3) ---
CATALOG_PATH = "runtime/catalog_ieU_seed.json"
catalog_cache = None

def load_catalog():
    global catalog_cache
    if catalog_cache:
        return catalog_cache
    
    if os.path.exists(CATALOG_PATH):
        import json
        try:
            with open(CATALOG_PATH, "r") as f:
                catalog_cache = json.load(f)
            return catalog_cache
        except Exception as e:
            print(f"Error loading catalog: {e}")
            return None
    return None

@app.get("/api/catalog/faculties")
def get_faculties():
    data = load_catalog()
    if not data:
        # Fallback minimal
        return [{"id": "fine_arts", "name": "Fine Arts & Design", "kpis": {}}]
    
    # Return list of faculties (id, name, kpis summary)
    return [
        {"id": f["id"], "name": f["name"], "kpis": f["kpis"]} 
        for f in data.get("faculties", [])
    ]

@app.get("/api/catalog/departments")
def get_departments(faculty_id: str):
    data = load_catalog()
    if not data:
        return []
    
    # Find faculty
    faculty = next((f for f in data["faculties"] if f["id"] == faculty_id), None)
    if not faculty:
        return []
    
    return [
        {"id": d["id"], "name": d["name"], "kpis": d["kpis"]}
        for d in faculty.get("departments", [])
    ]

@app.get("/api/kpi/scope")
def get_scope_kpis(scope: str = "campus", id: Optional[str] = None):
    data = load_catalog()
    if not data:
        # Emergency fallback to hardcoded campus
        return {
            "scope": "campus",
            "kpis": { "co2e_t": 18450, "energy_mwh": 14200, "water_m3": 45000, "intensity": 1.2, "progress": 42 },
            "levers": []
        }
    
    if scope == "campus":
        return {
            "scope": "campus",
            "name": "Campus Overview",
            "kpis": data["campus"]["kpis"],
            "levers": data["campus"].get("levers", [])
        }
    elif scope == "faculty":
        faculty = next((f for f in data["faculties"] if f["id"] == id), None)
        if not faculty:
            raise HTTPException(status_code=404, detail="Faculty not found")
        return {
            "scope": "faculty",
            "name": faculty["name"],
            "kpis": faculty["kpis"],
            "levers": faculty.get("levers", [])
        }
    elif scope == "department":
        # Search all faculties for this dept id
        dept = None
        for f in data["faculties"]:
            d = next((d for d in f.get("departments", []) if d["id"] == id), None)
            if d:
                dept = d
                break
        
        if not dept:
             raise HTTPException(status_code=404, detail="Department not found")
        
        return {
            "scope": "department",
            "name": dept["name"],
            "kpis": dept["kpis"],
            "levers": dept.get("levers", [])
        }
    
    return {}

# --- Endpoints ---

@app.get("/api/health")
def get_health():
    return {
        "ui": "OK",
        "api": "OK",
        "db": "OK",
        "n8n": "OK",
        "ts": int(time.time()),
        "status": state["system_status"]
    }

@app.get("/api/system/status")
def get_system_status():
    start_time = time.time()
    agents_status = "Running"
    if state["system_status"] != "OK":
        agents_status = "Degraded"
    
    latency = int((time.time() - start_time) * 1000) + random.randint(10, 50) # Simulate network + processing
    
    # Calculate backup status
    backup_text = "Today 04:00 AM"
    if state["last_backup"]["ts"]:
         # rough format "2m ago"
         diff = time.time() - datetime.datetime.fromisoformat(state["last_backup"]["ts"]).timestamp()
         if diff < 60:
             backup_text = "Just now"
         elif diff < 3600:
             backup_text = f"{int(diff/60)}m ago"
         else:
             backup_text = "Today"

    return {
        "system_state": state["system_status"],
        "brain": "Online",
        "agents": f"{agents_status} (4/4)",
        "backup": backup_text,
        "cache": "Ready",
        "last_incident": state["last_incident"],
        "latency_ms": latency,
        "updated_at": datetime.datetime.now().isoformat(),
        "backend_version": "v0.1.0"
    }

@app.get("/api/orchestrator/n8n/status")
def get_orchestrator_status():
    # Try to reach real n8n
    try:
        # Check n8n health (fake endpoint for demo logic or real if exists)
        # For this demo, we assume n8n is running if we can reach it, 
        # otherwise fallback to simulated state
        requests.get(f"{N8N_BASE_URL}/healthz", timeout=1) 
        
        # In a real scenario, we would fetch workflows from n8n API
        # For now, we simulate "Real" status if reachable
        return {
            "ok": True,
            "workflows": state["workflows"],
            "queue": {"pending": 0},
            "webhooks_last_ping": "Live"
        }
    except:
        # Fallback
        return {
            "ok": False,
            "workflows": state["workflows"],
            "queue": {"pending": random.randint(0, 5)},
            "webhooks_last_ping": "Offline (Seed)"
        }

@app.post("/api/orchestrator/n8n/run")
def run_workflow(payload: dict):
    # Demo-safe trigger
    wf_name = payload.get("workflow")
    return {"started": True, "run_id": f"exec_{int(time.time())}", "workflow": wf_name}

# --- Backup Endpoints ---

@app.post("/api/backup/run")
def run_backup():
    # Create backup
    ts = datetime.datetime.now().isoformat()
    filename = f"backup_{int(time.time())}.tar.gz"
    filepath = os.path.join(BACKUP_DIR, filename)
    
    # Create valid tar.gz of key files
    with tarfile.open(filepath, "w:gz") as tar:
        if os.path.exists("zero-campus.html"):
            tar.add("zero-campus.html")
        if os.path.exists("backend"):
            tar.add("backend")
            
    size = os.path.getsize(filepath)
    
    state["last_backup"] = {
        "ts": ts,
        "file": filename,
        "size": size
    }
    
    return {
        "ok": True,
        "file": filename,
        "size_bytes": size,
        "ts": ts
    }

@app.get("/api/backup/status")
def get_backup_status():
    lb = state["last_backup"]
    age = 0
    if lb["ts"]:
        age = int(time.time() - datetime.datetime.fromisoformat(lb["ts"]).timestamp())
        
    return {
        "last_ok_ts": lb["ts"],
        "last_file": lb["file"],
        "size_bytes": lb["size"],
        "age_seconds": age
    }
    
@app.post("/api/backup/verify")
def verify_backup():
    lb = state["last_backup"]
    if not lb["file"]:
        raise HTTPException(status_code=404, detail="No backup found")
        
    filepath = os.path.join(BACKUP_DIR, lb["file"])
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return {"ok": True}
    else:
        raise HTTPException(status_code=500, detail="Backup file missing or empty")

@app.post("/api/simulate/fail")
def simulate_fail():
    state["system_status"] = "DEGRADED"
    state["last_incident"] = "API Latency Spike detected"
    # Update agent status for visual impact
    state["workflows"][0]["status"] = "Retrying..."
    return {"status": "System set to DEGRADED"}

@app.post("/api/selfheal/run")
def self_heal():
    start = time.time()
    time.sleep(1) # Simulate work
    state["system_status"] = "HEALING"
    time.sleep(1)
    state["system_status"] = "OK"
    
    duration = int((time.time() - start) * 1000)
    
    # Log incident
    incident = {
        "ts": time.strftime("%H:%M:%S"),
        "type": "Latency Spike",
        "action": "Auto-Scale + Cache Flush",
        "result": "Resolved",
        "severity": "HIGH",
        "duration_ms": duration
    }
    state["incidents"].insert(0, incident)
    if len(state["incidents"]) > 5:
        state["incidents"].pop()
        
    state["last_incident"] = f"Resolved: {incident['type']}"
    
    # Restore agents
    state["workflows"][0]["status"] = "Running"
    
    return {"status": "System Healed", "incident": incident}

@app.get("/api/incidents/recent")
def get_incidents():
    return {"incidents": state["incidents"]}

@app.post("/api/brain/decide")
def brain_decide(context: dict):
    role = context.get("role", "Admin")
    role_lower = role.lower()
    
    intent = "General Overview"
    recommended_tabs = ["overview"]
    message = "Welcome to Zero@Campus."
    
    if role_lower == "dean":
        intent = "Strategic Overview"
        recommended_tabs = ["executive", "generator", "reporting"]
        message = "Focus on studio briefs + institutional output for Dean."
    elif role_lower == "facility":
        intent = "Operational Control"
        recommended_tabs = ["scopes", "forecast", "overview"]
        message = "Focus on energy forecasts + operational heatmap."
    elif role_lower == "sustainability":
        intent = "Compliance & Reporting"
        recommended_tabs = ["reporting", "roadmap", "overview"]
        message = "Focus on compliance reports + net-zero roadmap."
    else:
        intent = "General Overview"
        recommended_tabs = ["overview", "roadmap"]
        message = "General campus overview."

    return {
        "intent": intent,
        "recommended_tabs": recommended_tabs,
        "message": message,
        "ts": int(time.time()),
        "confidence": 0.95,
        "reason": f"Role '{role}' maps to strategic pillars."
    }

# --- Self-Heal Real Endpoints ---

@app.post("/api/selfheal/fail")
def real_fail():
    # Demo-only controlled failure
    state["system_status"] = "DEGRADED"
    
    incident = {
        "ts": time.strftime("%H:%M:%S"),
        "type": "api_failure_demo",
        "action": "restart_api",
        "result": "Pending",
        "severity": "HIGH",
        "duration_ms": 0
    }
    state["incidents"].insert(0, incident)
    if len(state["incidents"]) > 5:
        state["incidents"].pop()
        
    state["last_incident"] = "Critical Failure: API Unresponsive"
    return {"status": "System DEGRADED", "incident": incident}

@app.post("/api/selfheal/run")
def real_heal():
    # Simulate restart delay
    time.sleep(2) 
    
    state["system_status"] = "HEALING"
    time.sleep(1)
    state["system_status"] = "OK"
    
    # Find the pending incident and update it
    incident = None
    for inc in state["incidents"]:
        if inc["type"] == "api_failure_demo" and inc["result"] == "Pending":
            inc["result"] = "Recovered"
            inc["duration_ms"] = 12800 # Simulated restart time
            incident = inc
            break
            
    if not incident:
        # Fallback if no pending incident found
         incident = {
            "ts": time.strftime("%H:%M:%S"),
            "type": "api_restart_manual",
            "action": "restart_api",
            "result": "Recovered",
            "severity": "HIGH",
            "duration_ms": 12800
        }
         state["incidents"].insert(0, incident)

    state["last_incident"] = "System Recovered"
    state["workflows"][0]["status"] = "Running"
    
    return {"status": "System Restored", "incident": incident}

# --- Evidence Pack Endpoints ---
EVIDENCE_DIR = "runtime/evidence"

@app.post("/api/evidence/build")
def build_evidence_pack():
    ts = datetime.datetime.now().isoformat()
    pack_id = f"evidence_{int(time.time())}"
    zip_filename = f"{pack_id}.zip"
    zip_path = os.path.join(EVIDENCE_DIR, zip_filename)
    
    # Collect data for evidence.json
    evidence_data = {
        "timestamp": ts,
        "backend_version": "v0.1.0",
        "system_status": get_system_status(),
        "n8n_status": get_orchestrator_status(),
        "backup_status": get_backup_status(),
        "incidents": get_incidents(),
        "health": get_health()
    }
    
    # Create summary.md
    summary_md = f"""# Zero@Campus Evidence Pack
Generated: {ts}
Version: v0.1.0

## System Health
- State: {state['system_status']}
- Agents: 4/4 Running
- Latency: ~20ms

## Backup Status
- Last Backup: {state['last_backup']['file'] or 'None'}
- Size: {state['last_backup']['size']} bytes

## Recent Incidents
{len(state['incidents'])} incidents recorded.
"""

    # Write temp files and zip them
    import json
    import zipfile
    
    try:
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("evidence.json", json.dumps(evidence_data, indent=2))
            zf.writestr("summary.md", summary_md)
            # Add latest backup if exists
            if state['last_backup']['file']:
                backup_path = os.path.join(BACKUP_DIR, state['last_backup']['file'])
                if os.path.exists(backup_path):
                    zf.write(backup_path, arcname=f"backups/{state['last_backup']['file']}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    size = os.path.getsize(zip_path)
    
    return {
        "ok": True,
        "pack_id": pack_id,
        "zip_path": zip_path,
        "size_bytes": size,
        "created_at": ts
    }

from fastapi.responses import FileResponse

@app.get("/api/evidence/download")
def download_evidence(pack_id: str):
    zip_filename = f"{pack_id}.zip"
    zip_path = os.path.join(EVIDENCE_DIR, zip_filename)
    
    if os.path.exists(zip_path):
        return FileResponse(zip_path, media_type='application/zip', filename=zip_filename)
    else:
        raise HTTPException(status_code=404, detail="Evidence pack not found")

# --- Institutional Export Endpoints ---

@app.get("/api/export/gri.pdf")
def export_gri_pdf(scope: str = "campus", id: Optional[str] = None):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from pathlib import Path
    import time
    
    # Resolve Scope Name for Header
    scope_subtitle = "Campus Overview"
    data = load_catalog()
    if data:
        if scope == "faculty":
             f = next((x for x in data["faculties"] if x["id"] == id), None)
             if f: scope_subtitle = f"Faculty: {f['name']}"
        elif scope == "department":
             # naive search
             for f in data["faculties"]:
                 d = next((x for x in f.get("departments", []) if x["id"] == id), None)
                 if d: 
                     scope_subtitle = f"Department: {d['name']}"
                     break

    filename = f"Zero_Campus_GRI_{scope}_{id if id else 'all'}.pdf"
    filepath = os.path.join(EVIDENCE_DIR, filename)
    
    # Enterprise Header Setup
    BASE_DIR = Path(__file__).resolve().parents[1]
    # We will use text for Zero logo if image missing, but try to use what we have
    # Since we don't have a dedicated zero.logo.png yet, we'll create a placeholder or just use text.
    # But user asked to use assets/img/ieu-logo.png for IEU.
    LOGO_IEU = BASE_DIR / "assets/img/ieu-logo.png" 
    
    # Generate Evidence ID
    evid = f"EVID-{datetime.datetime.utcnow().strftime('%Y%m%d-%H%M')}-{scope}-{(id or 'campus')}"
    
    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4
    
    # 1. Enterprise Header (Clean White + Logos)
    # Top bar logic: Zero Logo (Left) | IEU Logo (Right) | Title (Center/Left)
    
    y = height - 60
    
    # Draw Zero@Campus Text Logo (Left)
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(colors.HexColor("#0a192f"))
    c.drawString(40, y, "Zero@Ecosystem")
    
    # Draw IEU Logo (Right)
    if LOGO_IEU.exists():
        try:
            # maintain aspect ratio approx
            c.drawImage(str(LOGO_IEU), width - 100, y - 10, width=60, height=60, mask='auto', preserveAspectRatio=True)
        except Exception:
            pass

    # Title & Metadata
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y - 30, "Zero@Campus — THE Impact Submission Checklist")
    
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawString(40, y - 46, f"Scope: {scope_subtitle}   •   Generated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}   •   {evid}")
    
    # Separator Line
    c.setStrokeColor(colors.HexColor("#FF6B00")) # Zero Orange
    c.setLineWidth(2)
    c.line(40, y - 55, width - 40, y - 55)
    
    # Reset Color
    c.setFillColor(colors.black)
    
    y = height - 140
    
    # A) What this means
    c.setFont("Helvetica", 10)
    text_lines = [
        "This checklist summarizes readiness for THE Impact submission.",
        "Statuses reflect data completeness and evidence availability for the selected scope.",
        "Use 'Pending Review' items to drive immediate data actions and assign owners."
    ]
    for line in text_lines:
        c.drawString(40, y, line)
        y -= 14
        
    y -= 10
    
    # B) Next Actions (Pilot)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Next Actions (Pilot)")
    y -= 16
    
    c.setFont("Helvetica", 10)
    actions = [
        "• SDG12: Complete procurement & waste data (Owner: Purchasing, Due: 7 days)",
        "• Validate energy/water meters & invoices (Owner: Facilities, Due: 48h)",
        "• Generate Evidence Pack ZIP and archive with ID (Owner: Sustainability, Due: 24h)"
    ]
    for act in actions:
        c.drawString(40, y, act)
        y -= 14
        
    y -= 30
    
    # 2. Executive Summary (System Health)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "1. System & Operational Status")
    y -= 30
    
    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"• System Health: {state['system_status']}")
    c.drawString(300, y, f"• Active Agents: 4/4 Running")
    y -= 20
    c.drawString(50, y, f"• Last Incident: {state['last_incident'] or 'None'}")
    c.drawString(300, y, f"• Last Backup: {state['last_backup']['file'] or 'None'}")
    y -= 40
    
    # 3. KPI Snapshot (Environmental)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "2. Environmental Performance (KPIs)")
    y -= 30
    
    # Draw KPI Box
    c.setStrokeColor(colors.HexColor("#eee"))
    c.setLineWidth(1)
    c.rect(40, y - 80, width - 80, 90, fill=0)
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y - 20, "Carbon Footprint")
    c.drawString(200, y - 20, "Energy Intensity")
    c.drawString(350, y - 20, "Net-Zero Gap")
    
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.HexColor("#0a192f"))
    c.drawString(50, y - 40, "18,450 tCO2e")
    c.drawString(200, y - 40, "1.2 tCO2e/stu")
    c.setFillColor(colors.HexColor("#D51635")) # Red for gap
    c.drawString(350, y - 40, "-58% to Target")
    
    y -= 120
    
    # 4. Recent Incidents Log
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "3. Recent Operational Incidents")
    y -= 20
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.gray)
    c.drawString(40, y, "Self-healing logs from the last 24 hours.")
    y -= 30
    
    c.setFont("Courier", 10)
    c.setFillColor(colors.black)
    
    if not state['incidents']:
        c.drawString(50, y, "No recent incidents recorded.")
    else:
        for inc in state['incidents'][:5]:
            line = f"[{inc['ts']}] {inc['severity']} - {inc['type']}: {inc['result']}"
            c.drawString(50, y, line)
            y -= 15

    # Footer
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.gray)
    c.drawString(40, 40, f"Generated by Zero@Ecosystem • Zero@Campus • {evid} • For pilot use — not an official disclosure.")
    c.drawCentredString(width/2, 40, "Page 1 of 1")
    
    c.save()
    
    return FileResponse(
        filepath, 
        media_type='application/pdf', 
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{evid}.pdf"'}
    )

@app.get("/api/export/csrd.xml")
def export_csrd_xml():
    from fastapi.responses import Response
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<CSRDReport xmlns="http://zero.campus/csrd/v1">
    <Metadata>
        <Organization>Zero University</Organization>
        <Period>{datetime.datetime.now().year}</Period>
        <Version>0.1.0</Version>
        <Generated>{datetime.datetime.now().isoformat()}</Generated>
    </Metadata>
    <Environmental>
        <ClimateChange>
            <Scope1>5200</Scope1>
            <Scope2>3250</Scope2>
            <Scope3>4800</Scope3>
            <Total>18450</Total>
            <Unit>tCO2e</Unit>
        </ClimateChange>
        <Water>
            <Consumption>15000</Consumption>
            <Unit>m3</Unit>
        </Water>
    </Environmental>
    <Social>
        <StudentEngagement>88%</StudentEngagement>
    </Social>
    <Governance>
        <SystemStatus>{state['system_status']}</SystemStatus>
        <LastAudit>{state['last_backup']['ts']}</LastAudit>
    </Governance>
</CSRDReport>
"""
    return Response(content=xml_content, media_type="application/xml")

@app.get("/api/export/the.pdf")
def export_the_pdf():
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    
    filename = "THE_Impact_Submission_Checklist.pdf"
    filepath = os.path.join(EVIDENCE_DIR, filename)
    
    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4
    
    # Header
    c.setFillColor(colors.HexColor("#FF6B00")) # Zero Orange
    c.rect(0, height - 80, width, 80, fill=1, stroke=0)
    
    # Partner Logo (IEU)
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOGO_PATH = os.path.join(PROJECT_ROOT, "assets", "img", "ieu-logo.jpg")
    
    if os.path.exists(LOGO_PATH):
        try:
            # Draw logo at top right
            logo_size = 50
            c.drawImage(LOGO_PATH, width - 80, height - 65, width=logo_size, height=logo_size, mask='auto')
        except Exception as e:
            print(f"Error drawing logo: {e}")

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 50, "THE Impact Ranking: Submission Checklist")
    
    # Content
    y = height - 120
    c.setFillColor(colors.black)
    
    items = [
        ("SDG 7: Affordable and Clean Energy", "Ready", "Energy consumption data validated."),
        ("SDG 11: Sustainable Cities", "Ready", "Transport & buildings data aggregated."),
        ("SDG 12: Responsible Consumption", "Pending Review", "Waste procurement data partial."),
        ("SDG 13: Climate Action", "Ready", "Carbon footprint calculation complete.")
    ]
    
    for sdg, status, note in items:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, sdg)
        y -= 20
        c.setFont("Helvetica", 12)
        c.drawString(50, y, f"Status: {status}")
        c.drawString(300, y, f"Note: {note}")
        y -= 40
        
    c.save()
    return FileResponse(filepath, media_type='application/pdf', filename=filename)

# Chart Data Endpoints (Seed Data)
@app.get("/api/charts/energy")
def get_energy_chart():
    # 30 days data
    actual = [random.randint(400, 600) for _ in range(30)]
    forecast = [random.randint(400, 600) for _ in range(30)]
    return {"actual": actual, "forecast": forecast}

@app.get("/api/charts/water")
def get_water_chart():
    actual = [random.randint(50, 100) for _ in range(30)]
    forecast = [random.randint(50, 100) for _ in range(30)]
    return {"actual": actual, "forecast": forecast}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8095)
