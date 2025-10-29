from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import os, redis, json, uuid, asyncio
from dotenv import load_dotenv
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
import time
from uuid import uuid4
from config import settings, validate_environment

# ===========================
# PYDANTIC MODELS
# ===========================

class Agent(BaseModel):
    name: str = Field(..., description="Unique agent name")
    role: str = Field(..., description="Agent's core function (e.g. 'QA', 'Debugger', 'Analyzer')")
    description: Optional[str] = Field(None, description="Detailed role or purpose")
    skills: List[str] = Field(default_factory=list, description="Capabilities or prompts")
    model: Optional[str] = Field("gpt-4o-mini", description="Default AI model for this agent")

class TaskRequest(BaseModel):
    job: str = Field(..., description="Task description")
    agent_name: Optional[str] = Field(None, description="Specific agent to handle the task")
    priority: Optional[str] = Field("normal", description="Task priority: low, normal, high")
    requires_qa: Optional[bool] = Field(False, description="Whether task needs QA review")

class AgentResponse(BaseModel):
    agent_name: str
    role: str
    output: str
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    review_needed: Optional[bool] = Field(False)

class EnhancedResult(BaseModel):
    job_id: str
    workflow_id: Optional[str] = Field(None, description="Associated workflow ID")
    parent_job_id: Optional[str] = Field(None, description="Parent job if this is a review/follow-up")
    agent: Optional[str] = Field(None, description="Agent name")
    role: Optional[str] = Field(None, description="Agent role")
    reviewed_by: Optional[str] = Field(None, description="Agent that reviewed this result")
    status: str = Field(default="completed", description="Task status: queued, processing, completed, failed")
    output: Optional[str] = Field(None, description="Task output")
    started_at: Optional[str] = Field(None, description="Task start time")
    completed_at: Optional[str] = Field(None, description="Task completion time")
    execution_time: Optional[float] = Field(None, description="Task execution time in seconds")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="Result timestamp")

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
# AGENT ORCHESTRATION HELPERS
# ===========================

async def auto_assign_agent(job_description: str) -> str:
    """Intelligently assign agent based on job description."""
    # Get all available agents
    agents = []
    for key in r.scan_iter("agent:*"):
        agents.append(json.loads(r.get(key)))
    
    if not agents:
        # Create default agent if none exist
        await create_default_agents()
        return "general_assistant"
    
    # Simple keyword-based assignment (can be enhanced with AI)
    job_lower = job_description.lower()
    
    # Role-based assignment logic
    if any(word in job_lower for word in ["test", "qa", "quality", "validate", "verify"]):
        return next((agent["name"] for agent in agents if agent["role"] == "QA"), "general_assistant")
    elif any(word in job_lower for word in ["debug", "fix", "error", "bug"]):
        return next((agent["name"] for agent in agents if agent["role"] == "Debugger"), "general_assistant")
    elif any(word in job_lower for word in ["analyze", "review", "audit", "inspect"]):
        return next((agent["name"] for agent in agents if agent["role"] == "Analyzer"), "general_assistant")
    elif any(word in job_lower for word in ["code", "develop", "implement", "create"]):
        return next((agent["name"] for agent in agents if agent["role"] == "Developer"), "general_assistant")
    
    return "general_assistant"

async def create_default_agents():
    """Initialize system with default agent roles."""
    default_agents = [
        {
            "name": "general_assistant",
            "role": "Assistant",
            "description": "General-purpose AI assistant for various tasks",
            "skills": ["general_help", "analysis", "writing"],
            "model": "gpt-4o-mini"
        },
        {
            "name": "analyzer_bot",
            "role": "Analyze", 
            "description": "Reads uploaded projects and generates structured analysis reports",
            "skills": ["code_summary", "file_classification", "architecture_analysis"],
            "model": "gpt-4o-mini"
        },
        {
            "name": "qa_bot",
            "role": "QA",
            "description": "Reviews AI outputs and scores their correctness",
            "skills": ["evaluation", "fact_check", "quality_review"],
            "model": "gpt-4o-mini"
        },
        {
            "name": "debugger_bot",
            "role": "Debug",
            "description": "Runs code lint and identifies errors or logic gaps",
            "skills": ["static_analysis", "error_fix", "performance_optimization"],
            "model": "gpt-4o-mini"
        }
    ]
    
    for agent_data in default_agents:
        key = f"agent:{agent_data['name']}"
        if not r.exists(key):
            agent_data["created_at"] = datetime.now().isoformat()
            agent_data["task_count"] = 0
            r.set(key, json.dumps(agent_data))

async def dispatch_task(job: dict):
    """Route a job to the most appropriate agent by role/keywords."""
    mode = job.get("mode", "Analyze").lower()
    agents = [json.loads(r.get(k)) for k in r.scan_iter("agent:*")]

    if not agents:
        raise HTTPException(status_code=400, detail="No agents registered.")

    # Keyword / role match
    keywords = {
        "analyze": "Analyze",
        "review": "QA",
        "qa": "QA",
        "debug": "Debug",
        "fix": "Debug",
        "security": "Security",
    }

    target_role = keywords.get(mode, mode)
    target = next((a for a in agents if a["role"].lower() == target_role.lower()), agents[0])

    job["dispatched_to"] = target["name"]
    job["assigned_role"] = target["role"]
    job["workflow_id"] = job.get("workflow_id", str(uuid4()))
    job["started_at"] = datetime.now().isoformat()

    r.lpush("queue", json.dumps(job))
    return {"status": "dispatched", "agent": target["name"], "workflow_id": job["workflow_id"]}

async def create_enhanced_result(job_id: str, agent_name: str, role: str, output: str, 
                               workflow_id: str = None, reviewed_by: str = None, 
                               confidence_score: float = None, execution_time: float = None,
                               parent_job_id: str = None) -> dict:
    """Create an enhanced result with full traceability."""
    result = {
        "job_id": job_id,
        "agent": agent_name,
        "role": role,
        "status": "completed",
        "output": output,
        "reviewed_by": reviewed_by,
        "confidence_score": confidence_score,
        "execution_time": execution_time,
        "timestamp": datetime.now().isoformat(),
        "workflow_id": workflow_id,
        "parent_job_id": parent_job_id
    }
    
    # Store result with expiry
    r.set(f"result:{job_id}", json.dumps(result), ex=3600)
    
    # Update agent statistics
    agent_key = f"agent:{agent_name.lower().replace(' ', '_')}"
    if r.exists(agent_key):
        agent_data = json.loads(r.get(agent_key))
        agent_data["last_completed"] = datetime.now().isoformat()
        agent_data["total_completions"] = agent_data.get("total_completions", 0) + 1
        r.set(agent_key, json.dumps(agent_data))
    
    return result

async def get_agent_chain_history(job_id: str) -> dict:
    """Get the full agent interaction chain for a job."""
    result_key = f"result:{job_id}"
    if not r.exists(result_key):
        return {"error": "Job result not found"}
    
    main_result = json.loads(r.get(result_key))
    chain = [main_result]
    
    # Find related jobs (reviews, follow-ups)
    for key in r.scan_iter("result:*"):
        result = json.loads(r.get(key))
        if result.get("parent_job_id") == job_id or result.get("workflow_id") == main_result.get("workflow_id"):
            if result["job_id"] != job_id:  # Avoid duplicating main result
                chain.append(result)
    
    return {
        "job_id": job_id,
        "chain_length": len(chain),
        "agents_involved": list(set(r["agent"] for r in chain)),
        "interaction_chain": sorted(chain, key=lambda x: x["timestamp"])
    }

# ===========================
# BASIC ROUTES
# ===========================

@app.get("/")
def home():
    return {"status": "running", "agent": "ProductForge Backend"}


@app.post("/task")
async def create_task(task: TaskRequest, bg: BackgroundTasks):
    """Enhanced task creation with agent dispatch and orchestration."""
    job_id = str(uuid.uuid4())
    
    # Auto-assign agent if not specified
    if not task.agent_name:
        task.agent_name = await auto_assign_agent(task.job)
    
    # Validate agent exists
    agent_key = f"agent:{task.agent_name.lower().replace(' ', '_')}"
    if not r.exists(agent_key):
        raise HTTPException(status_code=404, detail=f"Agent '{task.agent_name}' not found")
    
    # Create enhanced payload
    payload = {
        "job_id": job_id,
        "job": task.job,
        "agent_name": task.agent_name,
        "priority": task.priority,
        "requires_qa": task.requires_qa,
        "created_at": datetime.now().isoformat(),
        "mode": "agent_dispatch"
    }
    
    # Update agent task count
    agent_data = json.loads(r.get(agent_key))
    agent_data["task_count"] = agent_data.get("task_count", 0) + 1
    agent_data["last_assigned"] = datetime.now().isoformat()
    r.set(agent_key, json.dumps(agent_data))
    
    # Queue with priority
    queue_name = f"queue_{task.priority}" if task.priority != "normal" else "queue"
    r.lpush(queue_name, json.dumps(payload))
    
    return {"status": "queued", "job_id": job_id, "agent": task.agent_name, "task": payload}


@app.post("/dispatch_task")
async def dispatch_task_endpoint(payload: dict):
    """Accepts a job, determines its agent, and queues it."""
    job_id = str(uuid4())
    payload["job_id"] = job_id
    dispatch_info = await dispatch_task(payload)
    return {
        "status": "queued",
        "job_id": job_id,
        "dispatched_to": dispatch_info["agent"],
        "workflow_id": dispatch_info["workflow_id"],
    }


@app.get("/results")
def get_results():
    """Retrieve the latest 10 enhanced results with agent traceability."""
    results = []
    for key in r.scan_iter("result:*"):
        result = json.loads(r.get(key))
        # Add agent role and status for better display
        results.append(result)
    
    # Sort by timestamp and return latest 10
    sorted_results = sorted(results, key=lambda x: x.get("timestamp", ""), reverse=True)
    return {
        "results": sorted_results[:10],
        "total_results": len(results),
        "agents_active": len(set(r.get("agent", "unknown") for r in results))
    }

@app.get("/results/{job_id}")
async def get_result_details(job_id: str):
    """Get detailed result with full agent interaction chain."""
    return await get_agent_chain_history(job_id)

@app.get("/results/agent/{agent_name}")
def get_agent_results(agent_name: str, limit: int = 10):
    """Get results for a specific agent."""
    agent_results = []
    for key in r.scan_iter("result:*"):
        result = json.loads(r.get(key))
        if result.get("agent") == agent_name:
            agent_results.append(result)
    
    sorted_results = sorted(agent_results, key=lambda x: x.get("timestamp", ""), reverse=True)
    return {
        "agent": agent_name,
        "results": sorted_results[:limit],
        "total_tasks": len(agent_results),
        "success_rate": len([r for r in agent_results if r.get("output")]) / len(agent_results) * 100 if agent_results else 0
    }


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
def register_agent(agent: Agent):
    """Register a new AI agent with validation."""
    key = f"agent:{agent.name.lower().replace(' ', '_')}"
    if r.exists(key):
        raise HTTPException(status_code=400, detail="Agent already exists.")
    
    # Store agent with metadata
    agent_data = agent.dict()
    agent_data["created_at"] = datetime.now().isoformat()
    agent_data["task_count"] = 0
    
    r.set(key, json.dumps(agent_data))
    return {"status": "registered", "agent": agent_data}


@app.get("/agents")
def list_agents():
    """List all registered AI agents."""
    agents = []
    for key in r.scan_iter("agent:*"):
        agents.append(json.loads(r.get(key)))
    return {"count": len(agents), "agents": agents}

@app.get("/agents/{agent_name}")
def get_agent_details(agent_name: str):
    """Get detailed information about a specific agent."""
    key = f"agent:{agent_name.lower().replace(' ', '_')}"
    if not r.exists(key):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    agent_data = json.loads(r.get(key))
    
    # Get recent task history for this agent
    recent_tasks = []
    for result_key in r.scan_iter("result:*"):
        result = json.loads(r.get(result_key))
        if result.get("agent_name") == agent_name:
            recent_tasks.append({
                "job_id": result["job_id"],
                "job": result["job"][:100] + "..." if len(result["job"]) > 100 else result["job"],
                "timestamp": result.get("timestamp"),
                "success": bool(result.get("output"))
            })
    
    agent_data["recent_tasks"] = sorted(recent_tasks, 
                                      key=lambda x: x["timestamp"], 
                                      reverse=True)[:5]
    
    return {"agent": agent_data}


@app.delete("/agents/{name}")
def delete_agent(name: str):
    """Delete a specific agent."""
    key = f"agent:{name.lower().replace(' ', '_')}"
    if not r.exists(key):
        raise HTTPException(status_code=404, detail="Agent not found.")
    r.delete(key)
    return {"status": "deleted", "agent": name}

# ===========================
# MULTI-AGENT ORCHESTRATION
# ===========================

@app.post("/orchestrate")
async def orchestrate_workflow(task: TaskRequest):
    """Create a multi-agent workflow with QA chain."""
    workflow_id = str(uuid.uuid4())
    
    # Step 1: Primary agent handles the task
    primary_job_id = str(uuid.uuid4())
    primary_agent = await auto_assign_agent(task.job)
    
    primary_payload = {
        "job_id": primary_job_id,
        "workflow_id": workflow_id,
        "job": task.job,
        "agent_name": primary_agent,
        "priority": task.priority,
        "step": "primary",
        "created_at": datetime.now().isoformat()
    }
    
    r.lpush("queue", json.dumps(primary_payload))
    
    workflow_steps = [
        {"step": "primary", "agent": primary_agent, "job_id": primary_job_id, "status": "queued"}
    ]
    
    # Step 2: QA Review if requested
    if task.requires_qa:
        qa_job_id = str(uuid.uuid4())
        qa_payload = {
            "job_id": qa_job_id,
            "workflow_id": workflow_id,
            "job": f"Review and validate the output from {primary_agent} for: {task.job}",
            "agent_name": "qa_specialist",
            "priority": task.priority,
            "step": "qa_review",
            "depends_on": primary_job_id,
            "created_at": datetime.now().isoformat()
        }
        
        workflow_steps.append({
            "step": "qa_review", 
            "agent": "qa_specialist", 
            "job_id": qa_job_id, 
            "status": "waiting",
            "depends_on": primary_job_id
        })
    
    # Store workflow metadata
    workflow_data = {
        "workflow_id": workflow_id,
        "original_task": task.job,
        "steps": workflow_steps,
        "status": "running",
        "created_at": datetime.now().isoformat()
    }
    
    r.set(f"workflow:{workflow_id}", json.dumps(workflow_data))
    
    return {
        "status": "orchestrated",
        "workflow_id": workflow_id,
        "steps": workflow_steps,
        "estimated_completion": "2-5 minutes"
    }

@app.get("/workflows")
def list_workflows():
    """List all active and recent workflows."""
    workflows = []
    for key in r.scan_iter("workflow:*"):
        workflows.append(json.loads(r.get(key)))
    
    return {
        "total_workflows": len(workflows),
        "active": [w for w in workflows if w["status"] == "running"],
        "completed": [w for w in workflows if w["status"] == "completed"]
    }

@app.get("/workflows/{workflow_id}")
def get_workflow_status(workflow_id: str):
    """Get detailed status of a specific workflow."""
    key = f"workflow:{workflow_id}"
    if not r.exists(key):
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    workflow = json.loads(r.get(key))
    
    # Update step statuses by checking results
    for step in workflow["steps"]:
        result_key = f"result:{step['job_id']}"
        if r.exists(result_key):
            step["status"] = "completed"
            result = json.loads(r.get(result_key))
            step["output"] = result.get("output", "")[:200] + "..." if len(result.get("output", "")) > 200 else result.get("output", "")
        elif step["status"] == "queued":
            step["status"] = "processing"
    
    # Update overall workflow status
    completed_steps = [s for s in workflow["steps"] if s["status"] == "completed"]
    if len(completed_steps) == len(workflow["steps"]):
        workflow["status"] = "completed"
        workflow["completed_at"] = datetime.now().isoformat()
        r.set(key, json.dumps(workflow))
    
    return {"workflow": workflow}

# ===========================
# ADMIN AGENT & HIERARCHICAL COORDINATION
# ===========================

@app.post("/admin_review")
async def admin_review_task(job_id: str, review_prompt: str = "Evaluate this output for correctness, completeness, and adherence to requirements."):
    """Admin agent reviews completed task output."""
    result_key = f"result:{job_id}"
    if not r.exists(result_key):
        raise HTTPException(status_code=404, detail="Task result not found")
    
    original_result = json.loads(r.get(result_key))
    
    # Create admin review task
    review_job_id = str(uuid.uuid4())
    review_payload = {
        "job_id": review_job_id,
        "job": f"{review_prompt}\n\nOriginal Task: {original_result.get('job', 'Unknown')}\nAgent Output: {original_result.get('output', 'No output')}",
        "agent_name": "qa_bot",
        "mode": "admin_review",
        "original_job_id": job_id,
        "created_at": datetime.now().isoformat()
    }
    
    r.lpush("queue", json.dumps(review_payload))
    
    return {
        "status": "admin_review_queued",
        "review_job_id": review_job_id,
        "original_job_id": job_id,
        "reviewer": "qa_bot"
    }

@app.get("/agent_performance")
def get_agent_performance():
    """Get performance metrics for all agents."""
    performance = {}
    
    for key in r.scan_iter("agent:*"):
        agent_data = json.loads(r.get(key))
        agent_name = agent_data["name"]
        
        # Count completed tasks
        completed_tasks = 0
        total_tasks = 0
        recent_activity = []
        
        for result_key in r.scan_iter("result:*"):
            result = json.loads(r.get(result_key))
            if result.get("agent_name") == agent_name:
                total_tasks += 1
                if result.get("output"):
                    completed_tasks += 1
                
                recent_activity.append({
                    "timestamp": result.get("timestamp"),
                    "success": bool(result.get("output"))
                })
        
        success_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        performance[agent_name] = {
            "role": agent_data.get("role"),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "success_rate": round(success_rate, 2),
            "status": "active" if total_tasks > 0 else "idle",
            "last_active": max([a["timestamp"] for a in recent_activity], default=None) if recent_activity else None
        }
    
    return {
        "agent_performance": performance,
        "top_performer": max(performance.items(), key=lambda x: x[1]["success_rate"], default=(None, None))[0] if performance else None
    }

# ===========================
# MULTI-AGENT ORCHESTRATION DEMO
# ===========================

@app.post("/full_orchestration")
async def full_multi_agent_orchestration(task_description: str, enable_qa_chain: bool = True):
    """Demonstrate complete multi-agent orchestration with hierarchical command model."""
    orchestration_id = str(uuid.uuid4())
    
    # Ensure default agents exist
    await create_default_agents()
    
    # Step 1: Admin agent analyzes and plans the task
    admin_job_id = str(uuid.uuid4())
    admin_payload = {
        "job_id": admin_job_id,
        "job": f"As an admin agent, analyze this task and create an execution plan: {task_description}",
        "agent_name": "general_assistant",
        "mode": "admin_planning",
        "orchestration_id": orchestration_id,
        "step": "admin_analysis",
        "created_at": datetime.now().isoformat()
    }
    r.lpush("queue", json.dumps(admin_payload))
    
    # Step 2: Dispatch to specialized agent
    specialized_job_id = str(uuid.uuid4())
    assigned_agent = await auto_assign_agent(task_description)
    specialist_payload = {
        "job_id": specialized_job_id,
        "job": task_description,
        "agent_name": assigned_agent,
        "mode": "execution", 
        "orchestration_id": orchestration_id,
        "step": "specialist_execution",
        "parent_job_id": admin_job_id,
        "created_at": datetime.now().isoformat()
    }
    r.lpush("queue", json.dumps(specialist_payload))
    
    orchestration_steps = [
        {"step": "admin_analysis", "agent": "general_assistant", "job_id": admin_job_id, "status": "queued"},
        {"step": "specialist_execution", "agent": assigned_agent, "job_id": specialized_job_id, "status": "queued", "depends_on": admin_job_id}
    ]
    
    # Step 3: QA Review Chain (if enabled)
    if enable_qa_chain:
        qa_job_id = str(uuid.uuid4())
        qa_payload = {
            "job_id": qa_job_id,
            "job": f"Review and evaluate the specialist output for: {task_description}",
            "agent_name": "qa_bot",
            "mode": "qa_review",
            "orchestration_id": orchestration_id,
            "step": "qa_validation",
            "parent_job_id": specialized_job_id,
            "created_at": datetime.now().isoformat()
        }
        r.lpush("queue", json.dumps(qa_payload))
        
        orchestration_steps.append({
            "step": "qa_validation", 
            "agent": "qa_bot", 
            "job_id": qa_job_id, 
            "status": "queued",
            "depends_on": specialized_job_id
        })
        
        # Step 4: Final admin feedback
        final_job_id = str(uuid.uuid4())
        final_payload = {
            "job_id": final_job_id,
            "job": f"Provide final summary and recommendations based on all agent outputs for: {task_description}",
            "agent_name": "general_assistant",
            "mode": "admin_summary",
            "orchestration_id": orchestration_id,
            "step": "admin_feedback",
            "parent_job_id": qa_job_id,
            "created_at": datetime.now().isoformat()
        }
        r.lpush("queue", json.dumps(final_payload))
        
        orchestration_steps.append({
            "step": "admin_feedback",
            "agent": "general_assistant", 
            "job_id": final_job_id,
            "status": "queued",
            "depends_on": qa_job_id
        })
    
    # Store orchestration metadata
    orchestration_data = {
        "orchestration_id": orchestration_id,
        "original_task": task_description,
        "workflow_type": "full_multi_agent",
        "steps": orchestration_steps,
        "status": "running",
        "qa_enabled": enable_qa_chain,
        "created_at": datetime.now().isoformat(),
        "estimated_agents": len(set(step["agent"] for step in orchestration_steps))
    }
    
    r.set(f"orchestration:{orchestration_id}", json.dumps(orchestration_data), ex=7200)  # 2 hour expiry
    
    return {
        "status": "full_orchestration_initiated",
        "orchestration_id": orchestration_id,
        "workflow_type": "admin → specialist → qa → feedback",
        "steps": orchestration_steps,
        "agents_involved": list(set(step["agent"] for step in orchestration_steps)),
        "estimated_completion": "3-8 minutes",
        "qa_chain_enabled": enable_qa_chain
    }

@app.get("/orchestrations")
def list_orchestrations():
    """List all orchestrations with their current status."""
    orchestrations = []
    for key in r.scan_iter("orchestration:*"):
        orchestrations.append(json.loads(r.get(key)))
    
    return {
        "orchestrations": sorted(orchestrations, key=lambda x: x["created_at"], reverse=True),
        "total_orchestrations": len(orchestrations),
        "active_orchestrations": len([o for o in orchestrations if o["status"] == "running"])
    }

@app.get("/orchestrations/{orchestration_id}")
def get_orchestration_status(orchestration_id: str):
    """Get detailed orchestration status with all agent interactions."""
    key = f"orchestration:{orchestration_id}"
    if not r.exists(key):
        raise HTTPException(status_code=404, detail="Orchestration not found")
    
    orchestration = json.loads(r.get(key))
    
    # Update step statuses and collect outputs
    for step in orchestration["steps"]:
        result_key = f"result:{step['job_id']}"
        if r.exists(result_key):
            result = json.loads(r.get(result_key))
            step["status"] = "completed"
            step["output"] = result.get("output", "")[:300] + "..." if len(result.get("output", "")) > 300 else result.get("output", "")
            step["agent_role"] = result.get("role", "unknown")
            step["execution_time"] = result.get("execution_time")
            step["confidence"] = result.get("confidence_score")
        elif step["status"] == "queued":
            step["status"] = "processing"
    
    # Update overall status
    completed_steps = [s for s in orchestration["steps"] if s["status"] == "completed"]
    if len(completed_steps) == len(orchestration["steps"]):
        orchestration["status"] = "completed"
        orchestration["completed_at"] = datetime.now().isoformat()
        orchestration["total_execution_time"] = sum(s.get("execution_time", 0) for s in orchestration["steps"] if s.get("execution_time"))
        r.set(key, json.dumps(orchestration))
    
    return {
        "orchestration": orchestration,
        "progress": f"{len(completed_steps)}/{len(orchestration['steps'])}",
        "completion_percentage": round(len(completed_steps) / len(orchestration["steps"]) * 100, 1)
    }
