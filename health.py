#!/usr/bin/env python3
"""
FastAPI Health Check Server
Runs summarizer.py in the background and sends periodic health checks
"""

import asyncio
import subprocess
import sys
import threading
from datetime import datetime
from fastapi import FastAPI
from contextlib import asynccontextmanager
import httpx
import uvicorn

# =============================================================================
# CONFIGURATION
# =============================================================================

HEALTH_CHECK_URL = "https://penny-00h7.onrender.com"
HEALTH_CHECK_INTERVAL = 300  # 5 minutes in seconds
SUMMARIZER_SCRIPT = "summarizer.py"

# =============================================================================
# BACKGROUND TASKS
# =============================================================================

summarizer_process = None
health_check_task = None


def run_summarizer():
    """Run summarizer.py as a subprocess"""
    global summarizer_process
    try:
        print(f"Starting summarizer.py at {datetime.now()}")
        summarizer_process = subprocess.Popen(
            [sys.executable, SUMMARIZER_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # Monitor the process output
        while True:
            output = summarizer_process.stdout.readline()
            if output:
                print(f"[SUMMARIZER] {output.strip()}")
            
            # Check if process has ended
            if summarizer_process.poll() is not None:
                print(f"Summarizer process ended with code {summarizer_process.returncode}")
                break
                
    except Exception as e:
        print(f"Error running summarizer: {e}")


async def send_health_check():
    """Send periodic health checks to the specified URL"""
    while True:
        try:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(HEALTH_CHECK_URL)
                print(f"[{datetime.now()}] Health check sent to {HEALTH_CHECK_URL} - Status: {response.status_code}")
                
        except Exception as e:
            print(f"[{datetime.now()}] Error sending health check: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown"""
    # Startup
    print("="*50)
    print("FastAPI Health Check Server Starting")
    print("="*50)
    
    # Start summarizer in background thread
    summarizer_thread = threading.Thread(target=run_summarizer, daemon=True)
    summarizer_thread.start()
    print("Summarizer started in background thread")
    
    # Start health check task
    global health_check_task
    health_check_task = asyncio.create_task(send_health_check())
    print(f"Health check task started - sending to {HEALTH_CHECK_URL} every {HEALTH_CHECK_INTERVAL} seconds")
    
    yield
    
    # Shutdown
    print("\nShutting down gracefully...")
    
    # Cancel health check task
    if health_check_task:
        health_check_task.cancel()
        try:
            await health_check_task
        except asyncio.CancelledError:
            pass
    
    # Terminate summarizer process
    if summarizer_process:
        summarizer_process.terminate()
        try:
            summarizer_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            summarizer_process.kill()
    
    print("Shutdown complete")


# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

app = FastAPI(
    title="Summarizer Health Check Service",
    description="Runs summarizer.py and sends periodic health checks",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "status": "running",
        "service": "Summarizer Health Check Service",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    summarizer_status = "running" if summarizer_process and summarizer_process.poll() is None else "stopped"
    
    return {
        "status": "healthy",
        "summarizer_status": summarizer_status,
        "health_check_url": HEALTH_CHECK_URL,
        "health_check_interval": f"{HEALTH_CHECK_INTERVAL}s",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/status")
async def status():
    """Detailed status endpoint"""
    summarizer_running = summarizer_process and summarizer_process.poll() is None
    
    return {
        "service": "Summarizer Health Check Service",
        "summarizer": {
            "running": summarizer_running,
            "process_id": summarizer_process.pid if summarizer_running else None,
            "return_code": summarizer_process.returncode if not summarizer_running and summarizer_process else None
        },
        "health_check": {
            "url": HEALTH_CHECK_URL,
            "interval_seconds": HEALTH_CHECK_INTERVAL,
            "task_running": health_check_task and not health_check_task.done()
        },
        "timestamp": datetime.now().isoformat()
    }


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "health:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
