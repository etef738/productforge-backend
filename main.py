from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import os, redis, json, uuid, asyncio
from dotenv import load_dotenv
from datetime import datetime
from typing import Optional
from config import settings, validate_environment

# ===========================
# ENVIRONMENT & APP SETUP
# ===========================
load_dotenv()
validate_environment()

app = FastAPI(title="ProductForge Backend Agent")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "path": request.url.path}
    )

# Redis connection
r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))

# OpenAI client
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js local
        "https://*.netlify.app",   # Netlify preview/prod
        "https://yourdomain.com"   # add your domain(s)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===========================
# BASIC ROUTES
# ===========================

@app.get("/")
def home():
    return {"status": "running", "agent": "ProductForge Backend"}


@app.post("/task")
async def create_task(payload: dict, bg: BackgroundTasks):
    """Accepts a job and queues it to Redis."""
    job_id = str(uuid.uuid4())
    payload["job_id"] = job_id
    r.lpush("queue", json.dumps(payload))
    return {"status": "queued", "job_id": job_id, "task": payload}


@app.get("/results")
def get_results():
    """Retrieve the latest 10 results from Redis."""
    results = []
    for key in r.scan_iter("result:*"):
        results.append(json.loads(r.get(key)))
    return {"results": results[-10:]}


@app.get("/export/json")
def export_json():
    """Export all Redis results to a JSON file."""
    results = []
    for key in r.scan_iter("result:*"):
        results.append(json.loads(r.get(key)))

    file_path = "productforge_results.json"
    with open(file_path, "w") as f:
        json.dump(results, f, indent=2)

    return FileResponse(file_path, media_type="application/json", filename="productforge_results.json")


@app.get("/export/txt")
def export_txt():
    """Export all Redis results to a readable Markdown/TXT file."""
    results = []
    for key in r.scan_iter("result:*"):
        results.append(json.loads(r.get(key)))

    file_path = "productforge_results.txt"
    with open(file_path, "w") as f:
        f.write("# 🧠 ProductForge AI Agent Results\n\n")
        for res in results:
            job = res.get("job", "Unknown Task")
            output = res.get("output", "No output available.")
            f.write(f"## 🧩 Task:\n{job}\n\n")
            f.write(f"### 💡 Result:\n{output}\n\n")
            f.write(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")

    return FileResponse(file_path, media_type="text/plain", filename="productforge_results.txt")


# ===========================
# INTERACTIVE DASHBOARD
# ===========================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Interactive AI dashboard with export, upload, and live log streaming."""
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>ProductForge AI Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
.fade-in { animation: fadeIn 0.8s ease-in; }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.glow-processing {
  box-shadow: 0 0 10px #facc15, 0 0 25px #fbbf24, 0 0 40px #f59e0b;
  animation: pulseGlow 2s infinite alternate;
}
.glow-completed {
  box-shadow: 0 0 10px #22c55e, 0 0 25px #16a34a, 0 0 40px #15803d;
  animation: steadyGlow 3s infinite alternate;
}
.glow-error {
  box-shadow: 0 0 10px #ef4444, 0 0 25px #dc2626, 0 0 40px #991b1b;
  animation: flicker 0.15s infinite alternate;
}
@keyframes pulseGlow {
  from { opacity: 0.7; transform: scale(1); }
  to { opacity: 1; transform: scale(1.01); }
}
@keyframes steadyGlow {
  from { opacity: 0.85; }
  to { opacity: 1; }
}
@keyframes flicker {
  0% { opacity: 0.8; }
  50% { opacity: 1; }
  100% { opacity: 0.6; }
}
        </style>
    </head>
    <body class="bg-gray-900 text-gray-100 font-sans min-h-screen">

        <!-- Status Bar -->
        <div class="bg-gray-800 border-b border-indigo-600 text-center py-2 text-sm text-gray-300">
            🟢 <span id="status">Connected</span> |
            ⏱️ <span id="lastUpdated">Last Updated: loading...</span>
        </div>

        <div class="max-w-4xl mx-auto py-10 px-4">
            <h1 class="text-4xl font-bold text-center mb-8 text-indigo-400">
                ⚙️ ProductForge Agent Dashboard
            </h1>

            <!-- Task Form -->
            <form id="taskForm" class="mb-6 p-6 bg-gray-800 rounded-lg shadow-md border border-indigo-600">
                <label for="job" class="block text-lg font-semibold text-indigo-300 mb-2">Enter your task:</label>
                <textarea id="job" name="job" rows="3" placeholder="e.g., Analyze UI zip project"
                    class="w-full p-3 rounded bg-gray-700 text-gray-100 border border-gray-600 focus:outline-none focus:border-indigo-400"></textarea>
                <div class="flex flex-wrap gap-3 mt-4">
                    <button type="submit"
                        class="flex-1 bg-indigo-500 hover:bg-indigo-600 text-white font-bold py-2 px-4 rounded-lg transition">🚀 Send Task</button>
                    <button type="button" id="exportJson"
                        class="flex-1 bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded-lg transition">📥 Export JSON</button>
                    <button type="button" id="exportTxt"
                        class="flex-1 bg-yellow-500 hover:bg-yellow-600 text-white font-bold py-2 px-4 rounded-lg transition">📝 Export TXT</button>
                </div>
            </form>

            <!-- Worker Console -->
            <div class="p-4 mt-8 bg-gray-800 border border-indigo-600 rounded-lg shadow-md">
              <h2 class="text-2xl font-semibold text-indigo-400 mb-3">🧠 Worker Console</h2>
              <pre id="consoleLog" class="text-gray-300 text-sm h-64 overflow-y-auto bg-gray-900 p-3 rounded"></pre>
            </div>

            <!-- File Upload -->
            <form id="uploadForm" enctype="multipart/form-data"
                  class="p-6 bg-gray-800 rounded-lg shadow-md border border-indigo-600 mb-10 mt-8">
              <h2 class="text-2xl font-bold text-indigo-400 mb-4">📦 Upload Project ZIP</h2>
              <input type="file" id="zipFile" name="file" accept=".zip"
                     class="w-full text-sm text-gray-300 bg-gray-700 border border-gray-600 rounded-lg p-2 mb-4" />
              <input type="text" id="projectName" name="project"
                     placeholder="Project name (optional)"
                     class="w-full text-sm text-gray-300 bg-gray-700 border border-gray-600 rounded-lg p-2 mb-4" />
              <button type="submit"
                      class="w-full bg-purple-500 hover:bg-purple-600 text-white font-bold py-2 px-4 rounded-lg transition">
                ⬆️ Upload & Analyze
              </button>
            </form>

            <!-- Results -->
            <div id="results" class="space-y-6"></div>

            <footer class="text-center mt-10 text-gray-500 text-sm">
                Built by <span class="text-indigo-400 font-medium">Etefworkie Melaku</span> • Powered by FastAPI + OpenAI
            </footer>
        </div>

<script>
async function loadResults() {
  const response = await fetch('/results');
  const data = await response.json();
  const resultsDiv = document.getElementById('results');
  resultsDiv.innerHTML = '';
  data.results.forEach((item) => {
    const status = item.output ? "completed" : "processing";
    const glowClass = status === "completed" ? "glow-completed" : "glow-processing";
    const statusColor = status === "completed" ? "bg-green-600" : "bg-yellow-500 animate-pulse";
    const card = document.createElement('div');
    card.className = `p-6 bg-gray-800 rounded-lg shadow-md border border-indigo-600 fade-in ${glowClass}`;
    card.innerHTML = `
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-xl font-semibold text-indigo-300">🧩 Task</h2>
        <span class="text-xs text-white px-2 py-1 rounded-full ${statusColor}">
          ${status.toUpperCase()}
        </span>
      </div>
      <p class="text-lg text-gray-200 mb-4">${item.job}</p>
      <h3 class="text-lg font-semibold text-green-400">💡 Result:</h3>
      <p class="text-gray-300 whitespace-pre-wrap">${item.output || "⏳ Waiting..."}</p>
      <p class="text-xs text-gray-500 mt-4 text-right">🌸 ${new Date().toLocaleString()}</p>
    `;
    resultsDiv.appendChild(card);
  });
}
setInterval(loadResults, 10000);
loadResults();

// Live Worker Log Stream
const consoleLog = document.getElementById("consoleLog");
const evtSource = new EventSource("/stream");
evtSource.onmessage = (event) => {
  consoleLog.textContent += event.data + "\\n";
  consoleLog.scrollTop = consoleLog.scrollHeight;
};
evtSource.onerror = () => {
  consoleLog.textContent += "[⚠️ Connection lost, retrying...]\\n";
};
</script>

    </body>
    </html>
    """
    return html

# ===========================
# FILE UPLOAD
# ===========================

@app.post("/upload")
async def upload_zip(file: UploadFile = File(...), project: str = Form(default="")):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP files are allowed")
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")
    
    os.makedirs("workspace/uploads", exist_ok=True)
    dst = os.path.join("workspace", "uploads", file.filename)
    with open(dst, "wb") as f:
        f.write(content)

    job_id = str(uuid.uuid4())
    payload = {
        "job": f"Analyze uploaded archive: {file.filename}",
        "file_path": dst,
        "mode": "analyze",
        "project": project or "unknown",
        "job_id": job_id
    }
    r.lpush("queue", json.dumps(payload))
    return {"status": "uploaded", "path": dst, "job_id": job_id}


# ===========================
# LIVE WORKER LOG STREAM
# ===========================

@app.get("/stream")
async def stream_logs():
    """Stream live worker logs from log.txt file."""
    log_file = "workspace/logs/worker_log.txt"
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    async def event_stream():
        with open(log_file, "r") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line.strip()}\\n\\n"
                await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ===========================
# AGENT REGISTRY
# ===========================

@app.post("/register_agent")
def register_agent(agent: dict):
    """Register a new AI agent profile."""
    name = agent.get("name")
    if not name:
        return {"error": "Agent must have a name"}
    key = f"agent:{name.lower().replace(' ', '_')}"
    r.set(key, json.dumps(agent))
    return {"status": "registered", "agent": agent}


@app.get("/agents")
def list_agents():
    """List all registered AI agents."""
    agents = []
    for key in r.scan_iter("agent:*"):
        agents.append(json.loads(r.get(key)))
    return {"agents": agents}


@app.delete("/agents/{name}")
def delete_agent(name: str):
    """Delete a specific agent by name."""
    key = f"agent:{name.lower().replace(' ', '_')}"
    if r.exists(key):
        r.delete(key)
        return {"status": "deleted", "agent": name}
    return {"error": "Agent not found"}
