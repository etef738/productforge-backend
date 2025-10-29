import os
import json
import redis
import time
import datetime
from openai import OpenAI
from dotenv import load_dotenv

# ===========================
# INITIAL SETUP
# ===========================

load_dotenv()

# Connect to Redis
r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))

# Initialize OpenAI
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Log file path
LOG_DIR = "workspace/logs"
LOG_FILE = os.path.join(LOG_DIR, "worker_log.txt")

# Ensure directory exists
os.makedirs(LOG_DIR, exist_ok=True)


# ===========================
# LOGGING FUNCTION
# ===========================

def log_event(message: str):
    """Write both to terminal and to log file for the live dashboard."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)

    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ===========================
# MAIN WORKER LOOP
# ===========================

print("🧠 ProductForge Worker started — waiting for jobs...")
log_event("🧠 Worker online and monitoring Redis queue...")

while True:
    try:
        # Check for new jobs
        job_data = r.brpop("queue", timeout=5)
        if not job_data:
            continue  # no job found, keep polling

        _, raw_payload = job_data
        payload = json.loads(raw_payload)
        job_id = payload.get("job_id")
        job = payload.get("job")
        mode = payload.get("mode", "default")
        project = payload.get("project", "unknown")
        crew = payload.get("crew", False)

        # Log job start
        log_event(f"⚙️ Running job: {job_id} | mode={mode} | project={project} | crew={crew}")

        # ===========================
        # EXECUTE JOB VIA OPENAI
        # ===========================
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a ProductForge AI development assistant."},
                    {"role": "user", "content": job}
                ],
                max_tokens=800,
                temperature=0.7,
            )
            output = completion.choices[0].message.content.strip()
        except Exception as e:
            output = f"❌ OpenAI error: {str(e)}"
            log_event(output)

        # ===========================
        # SAVE RESULT
        # ===========================
        result = {
            "job_id": job_id,
            "job": job,
            "output": output,
            "mode": mode,
            "project": project,
            "timestamp": datetime.datetime.now().isoformat()
        }

        r.set(f"result:{job_id}", json.dumps(result), ex=3600)  # expire in 1 hour
        log_event(f"✅ Completed job: {job_id}")

    except KeyboardInterrupt:
        log_event("🛑 Worker manually stopped by user.")
        print("\nGraceful shutdown.")
        break

    except Exception as e:
        log_event(f"🚨 Unexpected error: {str(e)}")
        time.sleep(3)
