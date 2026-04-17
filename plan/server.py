"""
Sieve Test Runner — local backend API
Run: python3 server.py
Requires: pip install fastapi uvicorn

Windows: Git Bash (comes with Git for Windows) is used as the shell.
         Install from https://git-scm.com/download/win then run this script
         with the Python that lives on your PATH (e.g. in Git Bash: python server.py).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import os
import sys
import shutil

app = FastAPI(title="Sieve Test Runner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    command: str
    cwd: str = None
    timeout: int = 60


@app.get("/health")
def health():
    return {"status": "ok"}


def _bash_executable() -> str:
    """Return the path to bash — Git Bash on Windows, /bin/bash elsewhere."""
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        # Last resort: let subprocess find bash on PATH
        found = shutil.which("bash")
        if found:
            return found
        raise RuntimeError(
            "bash not found. Install Git for Windows from https://git-scm.com/download/win"
        )
    return "/bin/bash"


@app.post("/run")
def run_command(req: RunRequest):
    env = os.environ.copy()
    try:
        bash = _bash_executable()
        result = subprocess.run(
            req.command,
            shell=True,
            executable=bash,
            cwd=req.cwd,
            capture_output=True,
            text=True,
            timeout=req.timeout,
            env=env,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "ok": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Timed out after {req.timeout}s", "returncode": -1, "ok": False}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1, "ok": False}


if __name__ == "__main__":
    import uvicorn
    print("Sieve Test Runner API → http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765)
