
# pyrefly: ignore [missing-import]
from flask import Flask, request, jsonify
import subprocess
import os
import uuid
import threading
import sys
import json
import logging

# Disable Flask request logging to keep terminal clean
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

# Dictionary to store task status
tasks = {}

def run_video_script(task_id, data):
    # Use a unique filename per task ID to avoid conflicts
    input_filename = "input.json"
    input_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), input_filename)
    
    try:
        tasks[task_id] = "processing"
        
        # 1. Save unique input file
        print(f"[{task_id}] Saving input data to {input_path}...", flush=True)
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        # 2. Path to your parallel script
        tts_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts.py")
        
        output_filename = f"video_{task_id}.mp4"
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_filename)
        
        # 3. Detect venv python for Windows or fallback to current sys.executable
        venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "Scripts", "python.exe")
        python_to_use = venv_python if os.path.exists(venv_python) else sys.executable
        
        # 4. Run the script with UNBUFFERED output
        print(f"[{task_id}] Starting tts.py engine using {python_to_use}...", flush=True)
        
        process = subprocess.run(
            [python_to_use, "-u", tts_script, input_path, output_path], 
            stdout=sys.stdout, 
            stderr=sys.stderr,
            check=True
        )
        
        tasks[task_id] = "completed"
        print(f"[{task_id}] SUCCESS: Video generation and upload finished.", flush=True)

    except subprocess.CalledProcessError as e:
        print(f"[{task_id}] CRITICAL ERROR: tts.py script failed with exit code {e.returncode}", flush=True)
        tasks[task_id] = f"failed: script error {e.returncode}"
    except Exception as e:
        print(f"[{task_id}] SYSTEM ERROR: {e}", flush=True)
        tasks[task_id] = f"failed: {str(e)}"
    finally:
        # We no longer delete input.json here. 
        # Cleanup is now handled by the tts.py engine at the very end.
        print(f"[{task_id}] Subprocess finished. Verification and final cleanup handled by engine.", flush=True)

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    task_id = str(uuid.uuid4())
    tasks[task_id] = "queued"
    
    # Start the thread
    thread = threading.Thread(target=run_video_script, args=(task_id, data))
    thread.daemon = True  # Ensures thread closes if Flask closes
    thread.start()
    
    return jsonify({"status": "accepted", "task_id": task_id}), 202

@app.route("/status/<task_id>", methods=["GET"])
def get_status(task_id):
    status = tasks.get(task_id, "not_found")
    return jsonify({"task_id": task_id, "status": status})

if __name__ == "__main__":
    # debug=False is important when using threading to avoid double-execution
    app.run(host="0.0.0.0", port=5001, debug=False)