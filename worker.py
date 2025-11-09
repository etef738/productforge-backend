import os, redis, json, time, traceback
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel
from config import settings
from models import EnhancedResult

# =====================================
# ENVIRONMENT SETUP
# =====================================
load_dotenv()
r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =====================================
# LOG PATH (Railway + Local Compatible)
# Uses /tmp/logs on Railway (always writable) else workspace/logs locally.
# Mirrors logic in main.py /stream endpoint for consistency.
# =====================================
BASE_LOG_DIR = "/tmp/logs" if os.environ.get("RAILWAY_ENVIRONMENT") else "workspace/logs"
os.makedirs(BASE_LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(BASE_LOG_DIR, "worker_log.txt")


# =====================================
# DATA MODELS
# =====================================
# EnhancedResult now imported from models.py
# =====================================
# LOGGING UTILS
# =====================================
def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


# =====================================
# AGENT PROMPTS (SPEC AGENT STYLE)
# =====================================
SPEC_PROMPTS = {
    "Analyze": """You are a specialist AI engineer. 
Analyze the uploaded project or code for functionality, structure, and clarity.
Identify strengths, weaknesses, and possible improvements.""",

    "QA": """You are a quality assurance AI reviewer.
Evaluate the previous agent’s output for correctness, completeness, and accuracy.
Provide feedback or corrections if necessary.""",

    "Debug": """You are an AI debugger.
Inspect reported issues or code snippets and identify bugs, errors, and performance bottlenecks.
Suggest fixes or optimizations.""",

    "Admin": """You are the orchestration admin.
Review the results from all agents (Analyze, QA, Debug) and produce a final summary report.
Highlight action points and overall system health."""
}


# =====================================
# AI EXECUTION FUNCTION
# =====================================
def execute_ai_task(agent_name: str, role: str, job: dict) -> str:
    """Run OpenAI completion with contextual role prompt."""
    system_prompt = SPEC_PROMPTS.get(role, "You are an AI agent.")
    user_content = job.get("job", "No task description provided.")

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    )

    output = completion.choices[0].message.content.strip()
    return output


# =====================================
# WORKFLOW HANDLING
# =====================================
def handle_workflow(result: EnhancedResult):
    """Chain to next step in workflow if required (e.g., QA or Admin review)."""
    if result.role.lower() == "analyze":
        # Queue QA review job
        qa_job = {
            "workflow_id": result.workflow_id,
            "job": f"Review analysis from {result.agent}",
            "mode": "QA",
            "agent": "qa_bot",
            "role": "QA",
            "parent_job_id": result.job_id,
        }
        r.lpush("queue", json.dumps(qa_job))
        log(f"🔁 Queued QA review for workflow {result.workflow_id}")
    elif result.role.lower() == "qa":
        # Queue Admin feedback job
        admin_job = {
            "workflow_id": result.workflow_id,
            "job": f"Summarize QA feedback and finalize report",
            "mode": "Admin",
            "agent": "admin_bot",
            "role": "Admin",
            "parent_job_id": result.job_id,
        }
        r.lpush("queue", json.dumps(admin_job))
        log(f"🏁 Queued Admin summary for workflow {result.workflow_id}")


# =====================================
# MAIN WORKER LOOP
# =====================================
def send_heartbeat():
    r.set("worker:heartbeat", str(time.time()), ex=60)  # expires after 60s

def main():
    log("🧠 Multi-Agent Worker started and connected to Redis...")

    while True:
        send_heartbeat()
        try:
            job_data = r.brpop("queue", timeout=5)
            if not job_data:
                time.sleep(1)
                continue

            _, raw_job = job_data
            job = json.loads(raw_job)

            job_id = job.get("job_id", str(time.time()))
            agent_name = job.get("agent", "default_agent")
            role = job.get("role", "Analyze")
            workflow_id = job.get("workflow_id")
            log(f"⚙️ Processing job {job_id} | Role: {role} | Agent: {agent_name}")

            start_time = time.time()

            # Execute AI Task
            try:
                output = execute_ai_task(agent_name, role, job)
                status = "completed"
                confidence = 0.95
            except Exception as e:
                output = f"❌ AI execution failed: {str(e)}"
                status = "error"
                confidence = 0.0
                log(traceback.format_exc())

            end_time = time.time()
            exec_time = round(end_time - start_time, 2)

            result = EnhancedResult(
                job_id=job_id,
                agent=agent_name,
                role=role,
                output=output,
                status=status,
                workflow_id=workflow_id,
                confidence_score=confidence,
                started_at=datetime.fromtimestamp(start_time).isoformat(),
                completed_at=datetime.fromtimestamp(end_time).isoformat(),
                execution_time=exec_time
            )

            r.setex(f"result:{job_id}", 3600, result.model_dump_json())
            log(f"✅ Result saved for job {job_id} ({role}) — {status} in {exec_time}s")

            # Chain next workflow step if applicable
            handle_workflow(result)

        except KeyboardInterrupt:
            log("🛑 Worker stopped manually.")
            break
        except Exception as e:
            log(f"❌ Worker loop error: {str(e)}")
            log(traceback.format_exc())
            time.sleep(3)


if __name__ == "__main__":
    main()
