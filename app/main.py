from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import os, json, base64
from dotenv import load_dotenv
from app.llm_generator import generate_app_code, decode_attachments
from app.github_utils import (
    create_repo,
    create_or_update_file,
    enable_pages,
    generate_mit_license,
)
from app.notify import notify_evaluation_server
from app.github_utils import create_or_update_binary_file
from app.models import TaskRequest, TaskResponse, ErrorResponse, HealthResponse

load_dotenv()
USER_SECRET = os.getenv("USER_SECRET")
USERNAME = os.getenv("GITHUB_USERNAME")
PROCESSED_PATH = "/tmp/processed_requests.json"

app = FastAPI(
    title="Auto App Builder API",
    description="Automatically generates and deploys GitHub Pages applications from briefs",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# === Persistence for processed requests ===
def load_processed():
    if os.path.exists(PROCESSED_PATH):
        try:
            return json.load(open(PROCESSED_PATH))
        except json.JSONDecodeError:
            return {}
    return {}

def save_processed(data):
    json.dump(data, open(PROCESSED_PATH, "w"), indent=2)

# === Root endpoint - Welcome page ===
@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Auto App Builder API</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { color: #2563eb; }
            code {
                background: #f1f5f9;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
            }
            pre {
                background: #1e293b;
                color: #e2e8f0;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
            }
            .status {
                display: inline-block;
                padding: 4px 12px;
                background: #10b981;
                color: white;
                border-radius: 20px;
                font-size: 14px;
            }
            a {
                color: #2563eb;
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Auto App Builder API</h1>
            <p><span class="status">✓ Online</span></p>
            
            <h2>📡 Endpoint</h2>
            <p><code>POST /api-endpoint</code></p>
            
            <h2>📝 Usage Example</h2>
            <pre>curl -X POST https://YOUR-SPACE-URL/api-endpoint \\
  -H "Content-Type: application/json" \\
  -d '{
    "email": "student@example.com",
    "secret": "YOUR_SECRET",
    "task": "captcha-solver-abc123",
    "round": 1,
    "nonce": "unique-nonce-xyz",
    "brief": "Create a captcha solver app",
    "checks": [
      "Repo has MIT license",
      "README.md is professional"
    ],
    "evaluation_url": "https://example.com/notify",
    "attachments": []
  }'</pre>
            
            <h2>📚 Documentation</h2>
            <ul>
                <li><a href="/docs" target="_blank">Interactive API Docs (Swagger UI)</a> - Try it out here!</li>
                <li><a href="/redoc" target="_blank">Alternative Docs (ReDoc)</a></li>
            </ul>
            
            <h2>ℹ️ Status</h2>
            <p>Server is running and ready to accept requests.</p>
        </div>
    </body>
    </html>
    """

# === Health check endpoint ===
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    """Check if the service is running"""
    return {
        "status": "healthy",
        "service": "auto-app-builder",
        "endpoints": ["/api-endpoint"]
    }

# === Background task ===
def process_request(data: dict):
    round_num = data.get("round", 1)
    task_id = data["task"]
    print(f"⚙ Starting background process for task {task_id} (round {round_num})")

    attachments = data.get("attachments", [])
    saved_attachments = decode_attachments(attachments)
    print("Attachments saved:", saved_attachments)

    # Step 1: Get or create repo
    repo = create_repo(task_id, description=f"Auto-generated app for task: {data['brief']}")

    # Optional: fetch previous README for round 2
    prev_readme = None
    if round_num == 2:
        try:
            readme = repo.get_contents("README.md")
            prev_readme = readme.decoded_content.decode("utf-8", errors="ignore")
            print("📖 Loaded previous README for round 2 context.")
        except Exception:
            prev_readme = None

    gen = generate_app_code(
        data["brief"],
        attachments=attachments,
        checks=data.get("checks", []),
        round_num=round_num,
        prev_readme=prev_readme
    )

    files = gen.get("files", {})
    saved_info = gen.get("attachments", [])

    # Step 2: Round-specific logic
    if round_num == 1:
        print("🏗 Round 1: Building fresh repo...")
        # Add attachments
        for att in saved_info:
            path = att["name"]
            try:
                with open(att["path"], "rb") as f:
                    content_bytes = f.read()
                if att["mime"].startswith("text") or att["name"].endswith((".md", ".csv", ".json", ".txt")):
                    text = content_bytes.decode("utf-8", errors="ignore")
                    create_or_update_file(repo, path, text, f"Add attachment {path}")
                else:
                    create_or_update_binary_file(repo, path, content_bytes, f"Add binary {path}")
                    b64 = base64.b64encode(content_bytes).decode("utf-8")
                    create_or_update_file(repo, f"attachments/{att['name']}.b64", b64, f"Backup {att['name']}.b64")
            except Exception as e:
                print("⚠ Attachment commit failed:", e)
    else:
        print("🔁 Round 2: Revising existing repo...")

    # Step 3: Common steps for both rounds
    for fname, content in files.items():
        create_or_update_file(repo, fname, content, f"Add/Update {fname}")

    mit_text = generate_mit_license()
    create_or_update_file(repo, "LICENSE", mit_text, "Add MIT license")

    # Step 4: Handle GitHub Pages enablement
    if data["round"] == 1:
        pages_ok = enable_pages(task_id)
        pages_url = f"https://{USERNAME}.github.io/{task_id}/" if pages_ok else None
    else:
        pages_ok = True
        pages_url = f"https://{USERNAME}.github.io/{task_id}/"

    try:
        commit_sha = repo.get_commits()[0].sha
    except Exception:
        commit_sha = None

    payload = {
        "email": data["email"],
        "task": data["task"],
        "round": round_num,
        "nonce": data["nonce"],
        "repo_url": repo.html_url,
        "commit_sha": commit_sha,
        "pages_url": pages_url,
    }

    notify_evaluation_server(data["evaluation_url"], payload)

    processed = load_processed()
    key = f"{data['email']}::{data['task']}::round{round_num}::nonce{data['nonce']}"
    processed[key] = payload
    save_processed(processed)

    print(f"✅ Finished round {round_num} for {task_id}")


# === Main endpoint with Pydantic validation ===
@app.post(
    "/api-endpoint",
    response_model=TaskResponse,
    responses={
        200: {"model": TaskResponse, "description": "Request accepted and processing started"},
        401: {"model": ErrorResponse, "description": "Invalid secret"}
    },
    tags=["App Builder"],
    summary="Build or update an application",
    description="""
    Accepts a task brief and automatically:
    1. Generates code using LLM
    2. Creates/updates a GitHub repository
    3. Deploys to GitHub Pages
    4. Notifies the evaluation server
    
    The processing happens in the background, so you'll get an immediate 200 response.
    """
)
async def receive_request(task: TaskRequest, background_tasks: BackgroundTasks):
    """
    Accept a task request to build or update an application.
    
    - **Round 1**: Creates a new repository and deploys the app
    - **Round 2**: Updates the existing repository with modifications
    """
    print("📩 Received request:", task.model_dump())

    # Step 0: Verify secret
    if task.secret != USER_SECRET:
        print("❌ Invalid secret received.")
        raise HTTPException(status_code=401, detail="Invalid secret")

    processed = load_processed()
    key = f"{task.email}::{task.task}::round{task.round}::nonce{task.nonce}"

    # Duplicate detection
    if key in processed:
        print(f"⚠ Duplicate request detected for {key}. Re-notifying only.")
        prev = processed[key]
        notify_evaluation_server(task.evaluation_url, prev)
        return TaskResponse(
            status="ok",
            note="duplicate handled & re-notified"
        )

    # Schedule background task (non-blocking)
    background_tasks.add_task(process_request, task.model_dump())

    # Immediate HTTP 200 acknowledgment
    return TaskResponse(
        status="accepted",
        note=f"processing round {task.round} started")