from fastapi import FastAPI, BackgroundTasks
from openai import OpenAI
import os, redis, json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="ProductForge Backend Agent")

# Connect to Redis
r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))

# Initialize OpenAI client
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

@app.get("/")
def home():
    return {"status": "running", "agent": "ProductForge Backend"}

@app.post("/task")
async def create_task(payload: dict, bg: BackgroundTasks):
    """Accepts a job and runs it in the background."""
    r.lpush("queue", json.dumps(payload))
    bg.add_task(run_agent, payload)
    return {"queued": payload}

def run_agent(payload):
    """Agent logic that processes a task."""
    job = payload.get("job", "no job")
    print(f"⚙️ Running job: {job}")

    # Ask OpenAI to process
    response = client.responses.create(
        model="gpt-4.1",
        input=f"Perform the following development task: {job}"
    )

    # Print the output
    print("🧠 Agent Output:", response.output_text)
