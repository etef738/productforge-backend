import os, json, redis, time
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
r = redis.from_url(os.environ["REDIS_URL"])

print("🧵 Worker started. Waiting for jobs...")

while True:
    _, job_data = r.brpop("queue")
    payload = json.loads(job_data)
    job = payload.get("job", "no job")

    print(f"⚙️ Worker processing job: {job}")
    response = client.responses.create(
        model="gpt-4.1",
        input=f"Perform task: {job}"
    )
    print("✅ Result:", response.output_text)
    time.sleep(1)
