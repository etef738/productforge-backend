
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import os, redis, json, uuid, asyncio
import uvicorn
from dotenv import load_dotenv
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
import time
from uuid import uuid4
from config import settings, validate_environment
from models import EnhancedResult

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

# EnhancedResult now imported from models.py

# ===========================
# ENVIRONMENT & APP SETUP
# ===========================
load_dotenv()
validate_environment()

# Track backend startup time for health monitoring
BACKEND_START_TIME = time.time()

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
# SYSTEM HEALTH ENDPOINT
# ===========================
from fastapi import HTTPException
import openai
import redis
import time

@app.get("/system/status")
async def system_status():
    """Return current system health indicators for dashboard."""

    status = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "redis_connected": False,
        "openai_key_active": False,
        "worker_log_active": False,
        "worker_alive": False,
    }

    # ✅ Check Redis connection
    try:
        r = redis.from_url(os.getenv("REDIS_URL"))
        r.ping()
        status["redis_connected"] = True
    except Exception:
        status["redis_connected"] = False

    # ✅ Check OpenAI key validity
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key and api_key.startswith("sk-"):
            openai.api_key = api_key
            status["openai_key_active"] = True
    except Exception:
        status["openai_key_active"] = False

    # ✅ Check worker log file existence
    base_dir = "/tmp/logs" if os.environ.get("RAILWAY_ENVIRONMENT") else "workspace/logs"
    log_path = os.path.join(base_dir, "worker_log.txt")
    status["worker_log_active"] = os.path.exists(log_path)

    # ✅ Check if worker is alive via Redis queue heartbeat
    try:
        heartbeat_key = "worker:heartbeat"
        last_heartbeat = r.get(heartbeat_key)
        if last_heartbeat:
            status["worker_alive"] = True
    except Exception:
        status["worker_alive"] = False

    return status


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

@app.get("/system/health")
def system_health():
    """Enhanced system health check with uptime and Redis status."""
    try:
        # Check Redis connectivity
        redis_connected = r.ping()
        
        # Count active jobs in queue
        active_jobs = r.llen("queue")
        priority_queues = ["queue_high", "queue_low"]
        for queue in priority_queues:
            active_jobs += r.llen(queue)
        
        # Calculate uptime
        uptime_seconds = round(time.time() - BACKEND_START_TIME, 2)
        
        # Count total results in system
        total_results = len(list(r.scan_iter("result:*")))
        
        return {
            "status": "ok",
            "uptime_seconds": uptime_seconds,
            "uptime_human": f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m {int(uptime_seconds % 60)}s",
            "redis_connected": redis_connected,
            "active_jobs": active_jobs,
            "total_results": total_results,
            "timestamp": datetime.now().isoformat(),
            "version": "S+ Tier Enhanced"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "uptime_seconds": round(time.time() - BACKEND_START_TIME, 2),
            "redis_connected": False,
            "active_jobs": 0,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


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
        # Ensure 'task' field is present for dashboard display
        if "task" not in result:
            # Try to infer from job/job_id if possible
            result["task"] = result.get("job", result.get("job_id", "Unknown Task"))
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

@app.get("/results/workflow/{workflow_id}")
async def get_workflow_results(workflow_id: str):
    """Show entire agent chain for a workflow (Analyze→QA→Admin)."""
    workflow_results = []
    total_execution_time = 0
    
    for key in r.scan_iter("result:*"):
        result = json.loads(r.get(key))
        if result.get("workflow_id") == workflow_id:
            workflow_results.append(result)
            total_execution_time += result.get("execution_time", 0)
    
    if not workflow_results:
        raise HTTPException(status_code=404, detail="Workflow results not found")
    
    # Sort by timestamp to show progression
    sorted_results = sorted(workflow_results, key=lambda x: x.get("started_at", x.get("timestamp", "")))
    
    # Create workflow chain visualization
    chain_visualization = []
    for i, result in enumerate(sorted_results):
        step_icon = {
            "Analyze": "🔍", "QA": "✅", "Debug": "🐛", "Admin": "👥", "Assistant": "🤖"
        }.get(result.get("role", ""), "⚙️")
        
        chain_visualization.append({
            "step": i + 1,
            "icon": step_icon,
            "agent": result.get("agent"),
            "role": result.get("role"),
            "status": result.get("status", "completed"),
            "execution_time": result.get("execution_time"),
            "output_preview": result.get("output", "")[:200] + "..." if len(result.get("output", "")) > 200 else result.get("output", "")
        })
    
    return {
        "workflow_id": workflow_id,
        "total_steps": len(sorted_results),
        "total_execution_time": round(total_execution_time, 2),
        "workflow_status": "completed" if all(r.get("status") == "completed" for r in sorted_results) else "in_progress",
        "chain_visualization": chain_visualization,
        "detailed_results": sorted_results
    }

@app.get("/workflow/{workflow_id}/timeline")
async def get_workflow_timeline(workflow_id: str):
    """Return the ordered chain of agent events within one workflow."""
    timeline_events = []
    
    # Find all results for this workflow
    for key in r.scan_iter("result:*"):
        result = json.loads(r.get(key))
        if result.get("workflow_id") == workflow_id:
            timeline_events.append(result)
    
    if not timeline_events:
        raise HTTPException(status_code=404, detail="Workflow timeline not found")
    
    # Sort chronologically by started_at or timestamp
    sorted_events = sorted(
        timeline_events, 
        key=lambda x: x.get("started_at") or x.get("timestamp", "")
    )
    
    # Build timeline with step numbers and cumulative time
    timeline = []
    cumulative_time = 0
    
    for i, event in enumerate(sorted_events):
        execution_time = event.get("execution_time", 0)
        cumulative_time += execution_time
        
        timeline_entry = {
            "step": i + 1,
            "role": event.get("role", "Unknown"),
            "agent": event.get("agent", "unknown_agent"),
            "started_at": event.get("started_at") or event.get("timestamp"),
            "completed_at": event.get("completed_at"),
            "execution_time": execution_time,
            "cumulative_time": round(cumulative_time, 2),
            "status": event.get("status", "completed"),
            "confidence_score": event.get("confidence_score"),
            "job_id": event.get("job_id")
        }
        timeline.append(timeline_entry)
    
    # Calculate workflow statistics
    total_time = round(cumulative_time, 2)
    average_step_time = round(total_time / len(timeline), 2) if timeline else 0
    
    # Find bottlenecks (steps taking > 150% of average time)
    bottlenecks = [
        step for step in timeline 
        if step["execution_time"] > (average_step_time * 1.5) and average_step_time > 0
    ]
    
    return {
        "workflow_id": workflow_id,
        "timeline": timeline,
        "total_time": total_time,
        "total_steps": len(timeline),
        "average_step_time": average_step_time,
        "bottlenecks": bottlenecks,
        "workflow_status": "completed" if all(e.get("status") == "completed" for e in sorted_events) else "in_progress",
        "generated_at": datetime.now().isoformat()
    }

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

    # Get most recent task name
    task_name = "Unknown_Task"
    if results:
        latest = sorted(results, key=lambda x: x.get("timestamp", ""), reverse=True)[0]
        task_name = latest.get("task") or latest.get("job") or "Unknown_Task"
    # Sanitize for filename
    safe_task = ''.join(c if c.isalnum() else '_' for c in str(task_name))
    filename = f"ProductForge_{safe_task}.json"

    # Prepend task info to JSON
    export_content = {
        "task": task_name,
        "results": results
    }
    file_path = filename
    with open(file_path, "w") as f:
        json.dump(export_content, f, indent=2)

    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return FileResponse(file_path, media_type="application/json", filename=filename, headers=headers)


@app.get("/export/txt")
def export_txt():
    """Export all Redis results to a readable Markdown/TXT file."""
    results = []
    for key in r.scan_iter("result:*"):
        results.append(json.loads(r.get(key)))

    # Get most recent task name
    task_name = "Unknown_Task"
    if results:
        latest = sorted(results, key=lambda x: x.get("timestamp", ""), reverse=True)[0]
        task_name = latest.get("task") or latest.get("job") or "Unknown_Task"
    # Sanitize for filename
    safe_task = ''.join(c if c.isalnum() else '_' for c in str(task_name))
    filename = f"ProductForge_{safe_task}.txt"

    file_path = filename
    with open(file_path, "w") as f:
        f.write(f"## Task: {task_name}\n\n")
        f.write("# 🧠 ProductForge AI Agent Results\n\n")
        for res in results:
            job = res.get("job", "Unknown Task")
            output = res.get("output", "No output available.")
            f.write(f"## 🧩 Task:\n{job}\n\n")
            f.write(f"### 💡 Result:\n{output}\n\n")
            f.write(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")

    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return FileResponse(file_path, media_type="text/plain", filename=filename, headers=headers)

@app.get("/performance/export")
def export_performance_metrics(format: str = "json"):
    """Export aggregated agent performance metrics in JSON or CSV format."""
    import csv
    from io import StringIO
    
    # Aggregate performance data
    agent_metrics = {}
    
    # Get all agents
    for key in r.scan_iter("agent:*"):
        agent_data = json.loads(r.get(key))
        agent_name = agent_data["name"]
        agent_metrics[agent_name] = {
            "agent_name": agent_name,
            "role": agent_data.get("role", "Unknown"),
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "success_rate": 0.0,
            "total_execution_time": 0.0,
            "average_execution_time": 0.0,
            "fastest_job": float('inf'),
            "slowest_job": 0.0,
            "last_activity": None
        }
    
    # Process all results
    execution_times = {}
    for key in r.scan_iter("result:*"):
        result = json.loads(r.get(key))
        agent_name = result.get("agent") or result.get("agent_name")
        
        if agent_name and agent_name in agent_metrics:
            metrics = agent_metrics[agent_name]
            metrics["total_tasks"] += 1
            
            # Track success/failure
            if result.get("output") and result.get("status") != "error":
                metrics["successful_tasks"] += 1
            else:
                metrics["failed_tasks"] += 1
            
            # Track execution times
            exec_time = result.get("execution_time", 0)
            if exec_time and exec_time > 0:
                metrics["total_execution_time"] += exec_time
                metrics["fastest_job"] = min(metrics["fastest_job"], exec_time)
                metrics["slowest_job"] = max(metrics["slowest_job"], exec_time)
                
                if agent_name not in execution_times:
                    execution_times[agent_name] = []
                execution_times[agent_name].append(exec_time)
            
            # Track last activity
            timestamp = result.get("timestamp") or result.get("completed_at")
            if timestamp:
                if not metrics["last_activity"] or timestamp > metrics["last_activity"]:
                    metrics["last_activity"] = timestamp
    
    # Calculate derived metrics
    for agent_name, metrics in agent_metrics.items():
        if metrics["total_tasks"] > 0:
            metrics["success_rate"] = round(
                (metrics["successful_tasks"] / metrics["total_tasks"]) * 100, 2
            )
        
        if agent_name in execution_times and execution_times[agent_name]:
            metrics["average_execution_time"] = round(
                sum(execution_times[agent_name]) / len(execution_times[agent_name]), 2
            )
        
        # Handle infinite values
        if metrics["fastest_job"] == float('inf'):
            metrics["fastest_job"] = 0.0
        else:
            metrics["fastest_job"] = round(metrics["fastest_job"], 2)
        
        metrics["slowest_job"] = round(metrics["slowest_job"], 2)
        metrics["total_execution_time"] = round(metrics["total_execution_time"], 2)
    
    # Export based on format
    if format.lower() == "csv":
        # Generate CSV
        output = StringIO()
        if agent_metrics:
            fieldnames = list(next(iter(agent_metrics.values())).keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for metrics in agent_metrics.values():
                writer.writerow(metrics)
        
        csv_content = output.getvalue()
        output.close()
        
        # Write to file and return
        csv_file_path = "agent_performance_metrics.csv"
        with open(csv_file_path, "w") as f:
            f.write(csv_content)
        
        return FileResponse(
            csv_file_path, 
            media_type="text/csv", 
            filename="agent_performance_metrics.csv"
        )
    
    else:
        # Return JSON format
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "total_agents": len(agent_metrics),
            "metrics": list(agent_metrics.values()),
            "summary": {
                "total_tasks_across_agents": sum(m["total_tasks"] for m in agent_metrics.values()),
                "average_success_rate": round(
                    sum(m["success_rate"] for m in agent_metrics.values()) / len(agent_metrics) 
                    if agent_metrics else 0, 2
                ),
                "fastest_average_agent": min(
                    agent_metrics.items(), 
                    key=lambda x: x[1]["average_execution_time"] or float('inf'),
                    default=(None, None)
                )[0] if agent_metrics else None
            }
        }
        
        # Write to file for download
        json_file_path = "agent_performance_metrics.json"
        with open(json_file_path, "w") as f:
            json.dump(export_data, f, indent=2)
        
        return FileResponse(
            json_file_path,
            media_type="application/json",
            filename="agent_performance_metrics.json"
        )


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
/* Enhanced animations and visual effects */
.fade-in { 
  animation: fadeIn 0.8s ease-in; 
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Panel glow effects */
.glow-processing {
  box-shadow: 0 0 15px #facc15, 0 0 30px #fbbf24, 0 0 45px #f59e0b;
  animation: pulseGlow 2s infinite alternate;
}
.glow-completed {
  box-shadow: 0 0 15px #22c55e, 0 0 30px #16a34a, 0 0 45px #15803d;
  animation: steadyGlow 3s infinite alternate;
}
.glow-error {
  box-shadow: 0 0 15px #ef4444, 0 0 30px #dc2626, 0 0 45px #991b1b;
  animation: flicker 0.15s infinite alternate;
}

@keyframes pulseGlow {
  from { opacity: 0.7; transform: scale(1); }
  to { opacity: 1; transform: scale(1.02); }
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

/* Console terminal styling */
#consoleLog {
  scrollbar-width: thin;
  scrollbar-color: #4f46e5 #1f2937;
}
#consoleLog::-webkit-scrollbar {
  width: 6px;
}
#consoleLog::-webkit-scrollbar-track {
  background: #1f2937;
  border-radius: 3px;
}
#consoleLog::-webkit-scrollbar-thumb {
  background: #4f46e5;
  border-radius: 3px;
}

/* Agent performance cards */
.agent-card {
  transition: all 0.3s ease;
  border-left: 4px solid transparent;
}
.agent-card:hover {
  transform: translateY(-2px);
  border-left-color: #6366f1;
  box-shadow: 0 8px 25px rgba(99, 102, 241, 0.15);
}

/* Results cards enhanced */
.result-card {
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}
.result-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, transparent, #6366f1, transparent);
  transition: left 0.5s ease;
}
.result-card:hover::before {
  left: 100%;
}

/* Mobile responsive improvements */
@media (max-width: 768px) {
  .max-w-6xl {
    max-width: 100%;
    padding: 0 1rem;
  }
  
  .grid.xl\\:grid-cols-3 {
    grid-template-columns: 1fr;
  }
  
  .text-5xl {
    font-size: 2.5rem;
  }
}

/* Status bar enhancements */
.status-bar {
  backdrop-filter: blur(10px);
  background: rgba(31, 41, 55, 0.9);
}

/* Interactive elements */
button:focus {
  outline: 2px solid #6366f1;
  outline-offset: 2px;
}

/* Loading states */
.loading {
  position: relative;
  overflow: hidden;
}
.loading::after {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
  animation: loading 1.5s infinite;
}
@keyframes loading {
  0% { left: -100%; }
  100% { left: 100%; }
}
        </style>
    </head>
    <body class="bg-gray-900 text-gray-100 font-sans min-h-screen">

        <!-- Status Bar -->
        <div class="bg-gray-800 border-b border-indigo-600 text-center py-2 text-sm text-gray-300">
            🟢 <span id="status">Connected</span> |
            ⏱️ <span id="lastUpdated">Last Updated: loading...</span>
        </div>

                <div class="max-w-6xl mx-auto py-8 px-4">
                        <!-- System Health Widget -->
                        <div id="healthStatus" class="p-4 rounded-xl bg-gray-900 shadow-lg mb-4">
                            <h2 class="text-xl font-bold mb-2">🩺 System Health</h2>
                            <ul class="space-y-1 text-sm" id="healthList">
                                <li>Checking system status...</li>
                            </ul>
                        </div>
            <!-- Header Section -->
            <header class="text-center mb-12">
                <h1 class="text-5xl font-bold text-indigo-400 mb-3">
                    ⚙️ ProductForge Agent Dashboard
                </h1>
                <p class="text-gray-400 text-lg">Multi-Agent AI System • Real-time Processing • Advanced Analytics</p>
            </header>

            <!-- Main Dashboard Grid -->
            <div class="grid grid-cols-1 xl:grid-cols-3 gap-8 mb-8">
                
                <!-- Left Column: Input Controls -->
                <div class="xl:col-span-1 space-y-8">
                    
                    <!-- Task Submission Panel -->
                    <div class="bg-gray-800 rounded-xl shadow-lg border border-indigo-600 p-6">
                        <h2 class="text-2xl font-bold text-indigo-400 mb-6 flex items-center">
                            🚀 <span class="ml-2">Task Control</span>
                        </h2>
                        <form id="taskForm" class="space-y-4">
                            <div>
                                <label for="job" class="block text-sm font-semibold text-indigo-300 mb-2">Task Description:</label>
                                <textarea id="job" name="job" rows="4" 
                                    placeholder="Enter your AI agent task (e.g., 'Analyze uploaded project', 'Debug code issues', 'Generate report')"
                                    class="w-full p-4 rounded-lg bg-gray-700 text-gray-100 border border-gray-600 focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-400/50 resize-none transition-all"></textarea>
                            </div>
                            <div class="grid grid-cols-1 gap-3">
                                <button type="submit"
                                    class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 px-4 rounded-lg transition-all transform hover:scale-[1.02] active:scale-[0.98]">
                                    🚀 Send Task
                                </button>
                                <button type="button" id="fullOrchestration"
                                    class="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold py-3 px-4 rounded-lg transition-all transform hover:scale-[1.02] active:scale-[0.98]">
                                    🔄 Full Orchestration
                                </button>
                            </div>
                        </form>
                    </div>

                    <!-- File Upload Panel -->
                    <div class="bg-gray-800 rounded-xl shadow-lg border border-indigo-600 p-6">
                        <h2 class="text-2xl font-bold text-indigo-400 mb-6 flex items-center">
                            📦 <span class="ml-2">Project Upload</span>
                        </h2>
                        <form id="uploadForm" enctype="multipart/form-data" class="space-y-4">
                            <div>
                                <label class="block text-sm font-semibold text-indigo-300 mb-2">ZIP File:</label>
                                <input type="file" id="zipFile" name="file" accept=".zip"
                                    class="w-full text-sm text-gray-300 bg-gray-700 border border-gray-600 rounded-lg p-3 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-indigo-600 file:text-white hover:file:bg-indigo-700 transition-all" />
                            </div>
                            <div>
                                <label class="block text-sm font-semibold text-indigo-300 mb-2">Project Name (Optional):</label>
                                <input type="text" id="projectName" name="project"
                                    placeholder="e.g., 'My React App', 'API Backend'"
                                    class="w-full p-3 rounded-lg bg-gray-700 text-gray-100 border border-gray-600 focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-400/50 transition-all" />
                            </div>
                            <button type="submit"
                                class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 px-4 rounded-lg transition-all transform hover:scale-[1.02] active:scale-[0.98]">
                                ⬆️ Upload & Analyze
                            </button>
                        </form>
                    </div>

                    <!-- Export Controls Panel -->
                    <div class="bg-gray-800 rounded-xl shadow-lg border border-indigo-600 p-6">
                        <h2 class="text-2xl font-bold text-indigo-400 mb-6 flex items-center">
                            📄 <span class="ml-2">Export Data</span>
                        </h2>
                        <div class="grid grid-cols-1 gap-3">
                            <button id="exportJson"
                                class="w-full bg-green-600 hover:bg-green-700 text-white font-bold py-3 px-4 rounded-lg transition-all transform hover:scale-[1.02] active:scale-[0.98]">
                                📥 Export JSON
                            </button>
                            <button id="exportTxt"
                                class="w-full bg-yellow-600 hover:bg-yellow-700 text-white font-bold py-3 px-4 rounded-lg transition-all transform hover:scale-[1.02] active:scale-[0.98]">
                                📝 Export TXT
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Middle Column: Live Console -->
                <div class="xl:col-span-1">
                    <div class="bg-gray-800 rounded-xl shadow-lg border border-indigo-600 p-6 h-full">
                        <h2 class="text-2xl font-bold text-indigo-400 mb-6 flex items-center">
                            🧠 <span class="ml-2">Worker Console</span>
                        </h2>
                        <div class="bg-black/50 rounded-lg p-4 h-96">
                            <pre id="consoleLog" class="text-green-400 text-sm h-full overflow-y-auto font-mono leading-relaxed">
[💡 ProductForge Worker Console Ready]
[⚡ Waiting for tasks...]
                            </pre>
                        </div>
                    </div>
                </div>

                <!-- Right Column: Agent Performance -->
                <div class="xl:col-span-1">
                    <div class="bg-gray-800 rounded-xl shadow-lg border border-indigo-600 p-6 h-full">
                        <h2 class="text-2xl font-bold text-indigo-400 mb-6 flex items-center">
                            📊 <span class="ml-2">Agent Performance</span>
                        </h2>
                        <div id="agentPerformance" class="space-y-4 max-h-96 overflow-y-auto"></div>
                    </div>
                </div>
            </div>

            <!-- Results Section (Full Width) -->
            <div class="bg-gray-800 rounded-xl shadow-lg border border-indigo-600 p-6 mb-8">
                <h2 class="text-2xl font-bold text-indigo-400 mb-6 flex items-center">
                    ✨ <span class="ml-2">Live Results</span>
                </h2>
                <div id="results" class="space-y-6 max-h-96 overflow-y-auto"></div>
            </div>

            <footer class="text-center mt-10 text-gray-500 text-sm">
                Built by <span class="text-indigo-400 font-medium">Etefworkie Melaku</span> • Powered by FastAPI + OpenAI
            </footer>
                </div>
                <script>
                async function updateHealth() {
                    const list = document.getElementById("healthList");
                    try {
                        const res = await fetch("/system/status");
                        const data = await res.json();

                        list.innerHTML = `
                            <li>${data.redis_connected ? '✅ Redis connected' : '❌ Redis offline'}</li>
                            <li>${data.openai_key_active ? '✅ OpenAI key detected' : '⚠️ OpenAI key missing'}</li>
                            <li>${data.worker_alive ? '🟢 Worker alive' : '🔴 Worker not responding'}</li>
                            <li>${data.worker_log_active ? '📄 Log file active' : '🕓 Waiting for logs...'}</li>
                            <li class="text-xs text-gray-500 mt-1">Last checked: ${data.timestamp}</li>
                        `;
                    } catch (e) {
                        list.innerHTML = `<li>⚠️ Error fetching status</li>`;
                    }
                }

                setInterval(updateHealth, 10000);
                updateHealth();
                </script>

<script>
// Enhanced Results with Workflow Visualization
async function loadResults() {
  const response = await fetch('/results');
  const data = await response.json();
  const resultsDiv = document.getElementById('results');
  resultsDiv.innerHTML = '';
  
  data.results.forEach((item) => {
    const status = item.output && item.status !== 'error' ? "completed" : "processing";
    const glowClass = status === "completed" ? "glow-completed" : "glow-processing";
    const statusColor = status === "completed" ? "bg-green-600" : "bg-yellow-500 animate-pulse";
    
    // Role-based icons and colors
    const roleConfig = {
      'Analyze': { icon: '🔍', color: 'text-yellow-400' },
      'QA': { icon: '✅', color: 'text-green-400' }, 
      'Debug': { icon: '🐛', color: 'text-red-400' },
      'Admin': { icon: '👥', color: 'text-blue-400' },
      'Assistant': { icon: '🤖', color: 'text-purple-400' }
    };
    const config = roleConfig[item.role] || { icon: '⚙️', color: 'text-gray-400' };
    
    const card = document.createElement('div');
    card.className = `result-card p-6 bg-gray-700/50 rounded-xl border border-gray-600 hover:border-indigo-500 fade-in ${glowClass}`;
    card.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-3">
          <div class="text-3xl p-2 rounded-lg bg-gray-800">${config.icon}</div>
          <div>
            <h3 class="text-lg font-bold ${config.color}">${item.role || 'Task'}</h3>
            <p class="text-xs text-gray-400">${item.agent || 'Unknown Agent'}</p>
          </div>
        </div>
        <div class="flex gap-2 items-center">
          ${item.execution_time ? `<span class="text-xs text-gray-400 bg-gray-800 px-2 py-1 rounded">${item.execution_time}s</span>` : ''}
          <span class="text-xs text-white px-3 py-1 rounded-full font-semibold ${statusColor}">
            ${status.toUpperCase()}
          </span>
        </div>
      </div>
      
      <div class="mb-4">
        <h4 class="text-sm font-semibold text-indigo-300 mb-2">📋 Task:</h4>
        <p class="text-gray-200 bg-gray-800/50 p-3 rounded-lg text-sm">${item.job || 'No task description'}</p>
      </div>
      
      <div class="mb-4">
        <h4 class="text-sm font-semibold text-green-400 mb-2">💡 Result:</h4>
        <div class="bg-black/30 p-4 rounded-lg border-l-4 border-green-500">
          <p class="text-gray-300 whitespace-pre-wrap text-sm leading-relaxed">${item.output || "⏳ Processing..."}</p>
        </div>
      </div>
      
      <div class="flex justify-between items-center text-xs text-gray-500">
        <div class="flex gap-4">
          ${item.workflow_id ? `<span class="text-indigo-400">🔗 ${item.workflow_id.substring(0, 8)}...</span>` : ''}
          ${item.confidence_score ? `<span class="text-yellow-400">🎯 ${Math.round(item.confidence_score * 100)}%</span>` : ''}
        </div>
        <span>⏰ ${new Date().toLocaleString()}</span>
      </div>
    `;
    resultsDiv.appendChild(card);
  });
}

// Enhanced Agent Performance with Better Visuals
async function loadAgentPerformance() {
  try {
    const response = await fetch('/agents');
    const data = await response.json();
    const performanceDiv = document.getElementById('agentPerformance');
    performanceDiv.innerHTML = '';
    
    // Show loading state
    performanceDiv.innerHTML = '<div class="loading bg-gray-700 rounded-lg p-4 h-20"></div>';
    
    setTimeout(() => {
      performanceDiv.innerHTML = '';
      
      if (data.agents && data.agents.length > 0) {
        data.agents.forEach((agent, index) => {
          const statusColor = agent.task_count > 0 ? 'text-green-400' : 'text-gray-400';
          const statusIcon = agent.task_count > 0 ? '🟢' : '⚪';
          
          const card = document.createElement('div');
          card.className = 'agent-card p-4 bg-gray-700/80 rounded-lg border border-gray-600 hover:border-indigo-500 transition-all';
          card.style.animationDelay = `${index * 0.1}s`;
          card.innerHTML = `
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2">
                <span class="text-lg">${getAgentIcon(agent.role)}</span>
                <h3 class="text-sm font-bold text-indigo-300">${agent.name}</h3>
              </div>
              <span class="text-xs ${statusColor}">${statusIcon}</span>
            </div>
            <p class="text-xs text-gray-400 mb-3">${agent.role}</p>
            <div class="text-xs space-y-1">
              <div class="flex justify-between">
                <span>Tasks:</span>
                <span class="text-indigo-400 font-semibold">${agent.task_count || 0}</span>
              </div>
              <div class="flex justify-between">
                <span>Status:</span>
                <span class="${statusColor}">${agent.task_count > 0 ? 'Active' : 'Standby'}</span>
              </div>
            </div>
          `;
          card.classList.add('fade-in');
          performanceDiv.appendChild(card);
        });
      } else {
        performanceDiv.innerHTML = `
          <div class="text-center text-gray-400 p-6">
            <div class="text-3xl mb-2">🤖</div>
            <p>No agents registered yet</p>
            <p class="text-xs mt-1">Agents will appear when tasks are submitted</p>
          </div>
        `;
      }
    }, 800);
    
  } catch (error) {
    console.error('Failed to load agent performance:', error);
    const performanceDiv = document.getElementById('agentPerformance');
    performanceDiv.innerHTML = `
      <div class="text-center text-red-400 p-4">
        <div class="text-2xl mb-2">⚠️</div>
        <p class="text-sm">Failed to load agents</p>
      </div>
    `;
  }
}

// Helper function for agent icons
function getAgentIcon(role) {
  const icons = {
    'Analyze': '🔍',
    'QA': '✅', 
    'Debug': '🐛',
    'Admin': '👥',
    'Assistant': '🤖',
    'Analyzer': '🔍'
  };
  return icons[role] || '⚙️';
}

// Enhanced task submission with full orchestration option
document.getElementById('taskForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const job = document.getElementById('job').value;
  
  try {
    const response = await fetch('/task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job: job })
    });
    
    if (response.ok) {
      document.getElementById('job').value = '';
      loadResults();
    }
  } catch (error) {
    console.error('Failed to submit task:', error);
  }
});

// Full orchestration button
document.getElementById('fullOrchestration').addEventListener('click', async () => {
  const job = document.getElementById('job').value;
  if (!job) return;
  
  try {
    const response = await fetch('/full_orchestration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        task_description: job,
        enable_qa_chain: true 
      })
    });
    
    if (response.ok) {
      document.getElementById('job').value = '';
      loadResults();
    }
  } catch (error) {
    console.error('Failed to start orchestration:', error);
  }
});

// Auto-refresh functions
setInterval(() => {
  loadResults();
  loadAgentPerformance();
}, 10000);

// Initial load
loadResults();
loadAgentPerformance();

// Enhanced Export Functions
document.getElementById('exportJson').addEventListener('click', () => {
  window.open('/export/json', '_blank');
});

document.getElementById('exportTxt').addEventListener('click', () => {
  window.open('/export/txt', '_blank');
});

// Enhanced File Upload Handler
document.getElementById('uploadForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData();
  const fileInput = document.getElementById('zipFile');
  const projectName = document.getElementById('projectName').value;
  
  if (!fileInput.files[0]) {
    alert('Please select a ZIP file to upload');
    return;
  }
  
  formData.append('file', fileInput.files[0]);
  formData.append('project', projectName);
  
  const uploadButton = e.target.querySelector('button[type="submit"]');
  const originalText = uploadButton.innerHTML;
  uploadButton.innerHTML = '⏳ Uploading...';
  uploadButton.disabled = true;
  
  try {
    const response = await fetch('/upload', {
      method: 'POST',
      body: formData
    });
    
    if (response.ok) {
      const result = await response.json();
      fileInput.value = '';
      document.getElementById('projectName').value = '';
      
      // Add success message to console
      const consoleLog = document.getElementById('consoleLog');
      consoleLog.textContent += `[✅ Upload Success] ${result.job_id}\\n`;
      consoleLog.scrollTop = consoleLog.scrollHeight;
      
      loadResults();
    } else {
      throw new Error('Upload failed');
    }
  } catch (error) {
    console.error('Upload failed:', error);
    alert('Upload failed. Please try again.');
  } finally {
    uploadButton.innerHTML = originalText;
    uploadButton.disabled = false;
  }
});

// Live Worker Log Stream with Enhanced Features
const consoleLog = document.getElementById("consoleLog");
let eventSource;

function connectToStream() {
  if (eventSource) {
    eventSource.close();
  }
  
  eventSource = new EventSource("/stream");
  
  eventSource.onopen = () => {
    document.getElementById('status').textContent = 'Connected';
    document.getElementById('status').className = 'text-green-400';
  };
  
  eventSource.onmessage = (event) => {
    const timestamp = new Date().toLocaleTimeString();
    consoleLog.textContent += `[${timestamp}] ${event.data}\\n`;
    consoleLog.scrollTop = consoleLog.scrollHeight;
    
    // Update last updated time
    document.getElementById('lastUpdated').textContent = `Last Updated: ${timestamp}`;
  };
  
  eventSource.onerror = () => {
    document.getElementById('status').textContent = 'Reconnecting...';
    document.getElementById('status').className = 'text-yellow-400';
    consoleLog.textContent += "[⚠️ Connection lost, retrying...]\\n";
    consoleLog.scrollTop = consoleLog.scrollHeight;
    
    // Attempt to reconnect after a delay
    setTimeout(connectToStream, 3000);
  };
}

connectToStream();

// Update status bar periodically
setInterval(() => {
  fetch('/system/health')
    .then(response => response.json())
    .then(data => {
      if (data.status === 'ok') {
        document.getElementById('status').textContent = `Connected (${data.uptime_human})`;
        document.getElementById('status').className = 'text-green-400';
      }
    })
    .catch(() => {
      document.getElementById('status').textContent = 'Connection Issues';
      document.getElementById('status').className = 'text-red-400';
    });
}, 30000);
</script>

    </body>
    </html>
    """
    return html

# ===========================
# FILE UPLOAD
# ===========================

# Railway-compatible upload directory
UPLOAD_DIR = "/tmp/uploads" if os.environ.get("RAILWAY_ENVIRONMENT") else "workspace/uploads"

@app.post("/upload")
async def upload_zip(file: UploadFile = File(...), project: str = Form(default="")):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP files are allowed")
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    dst = os.path.join(UPLOAD_DIR, file.filename)
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
    """Stream live worker logs (Railway + local compatible)."""

    import os, asyncio
    from fastapi.responses import StreamingResponse

    # ✅ Use /tmp/logs for Railway (always writable) or fallback to local
    base_dir = "/tmp/logs" if os.environ.get("RAILWAY_ENVIRONMENT") else "workspace/logs"
    os.makedirs(base_dir, exist_ok=True)
    log_file = os.path.join(base_dir, "worker_log.txt")

    async def event_stream():
        # ✅ If file doesn’t exist yet, wait until it’s created
        while not os.path.exists(log_file):
            yield "data: [Waiting for worker log file to be created...]\n\n"
            await asyncio.sleep(1)

        # ✅ Stream the live log updates
        with open(log_file, "r") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line.strip()}\n\n"
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
    """Get enhanced performance metrics for all agents with success counts and average durations."""
    performance = {}
    
    for key in r.scan_iter("agent:*"):
        agent_data = json.loads(r.get(key))
        agent_name = agent_data["name"]
        
        # Enhanced metrics tracking
        completed_tasks = 0
        total_tasks = 0
        failed_tasks = 0
        total_execution_time = 0
        execution_times = []
        recent_activity = []
        
        for result_key in r.scan_iter("result:*"):
            result = json.loads(r.get(result_key))
            if result.get("agent") == agent_name or result.get("agent_name") == agent_name:
                total_tasks += 1
                
                # Track execution time
                exec_time = result.get("execution_time", 0)
                if exec_time:
                    execution_times.append(exec_time)
                    total_execution_time += exec_time
                
                # Track success/failure
                if result.get("output") and result.get("status") != "error":
                    completed_tasks += 1
                else:
                    failed_tasks += 1
                
                recent_activity.append({
                    "timestamp": result.get("timestamp"),
                    "success": bool(result.get("output") and result.get("status") != "error"),
                    "execution_time": exec_time
                })
        
        success_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        avg_duration = (total_execution_time / len(execution_times)) if execution_times else 0
        
        performance[agent_name] = {
            "role": agent_data.get("role"),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "success_rate": round(success_rate, 2),
            "average_duration": round(avg_duration, 2),
            "total_execution_time": round(total_execution_time, 2),
            "status": "active" if total_tasks > 0 else "idle",
            "last_active": None,  # Simplified for stability
            "recent_performance": recent_activity[-5:] if recent_activity else []
        }
    
    # Calculate top performer and fastest agent safely
    top_performer = None
    fastest_agent = None
    
    if performance:
        # Find top performer by success rate
        active_performers = [(name, stats) for name, stats in performance.items() if stats["success_rate"] > 0]
        if active_performers:
            top_performer = max(active_performers, key=lambda x: x[1]["success_rate"])[0]
        
        # Find fastest agent by average duration
        active_agents = [(name, stats) for name, stats in performance.items() if stats["average_duration"] > 0]
        if active_agents:
            fastest_agent = min(active_agents, key=lambda x: x[1]["average_duration"])[0]
    
    return {
        "agent_performance": performance,
        "top_performer": top_performer,
        "fastest_agent": fastest_agent
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


# ===========================
# APPLICATION STARTUP
# ===========================

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
