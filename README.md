# YouTube Automation
![Project Banner](https://raw.githubusercontent.com/your-repo/your-project/main/assets/banner.png)
## Overview
This repository implements an **automated YouTube video creation pipeline**. It combines AI-generated scripts, image generation, text‑to‑speech, video stitching, and automated upload to YouTube via a Flask API and an accompanying n8n workflow.
- **Flask server** (`server.py`) handles HTTP requests to start the generation process and query job status.
- **`tts.py`** orchestrates the core workflow: loads input JSON, generates images using Pollinations AI, creates speech with Edge‑TTS, composes video clips with MoviePy, and uploads the final video to Google Drive.
- **n8n workflow** (`youtube agent.json`) ties the API endpoints together, formats prompts for a language model, and triggers the Flask service.
- **Google Drive** is used for temporary storage and as a source for the final video file.
- **YouTube integration** uploads the completed video to a YouTube channel.
The system is designed for **scalable, headless operation** and can be invoked programmatically from any client.
---
## Features
- End‑to‑end automation from story generation to YouTube upload.
- Dynamic image generation with **Flux** models (anime, realism, 3D).
- High‑quality speech synthesis using **Edge‑TTS**.
- Video compositing with **MoviePy** (Ken Burns zoom, fade‑in/out effects).
- Robust error handling and retry logic for API rate limits.
- Clean-up of temporary assets after completion.
- Configurable via environment variables and JSON input.
---
## Prerequisites
- **Python 3.9+** (tested on 3.11).
- **Virtual environment** (recommended).
- Google API credentials (`credentials.json`) for Drive access.
- OpenRouter API key (set as `Authorization` header in the n8n HTTP request).
- **ffmpeg** installed and available in `PATH` (required by MoviePy).
- Internet connectivity for image generation and TTS.
---
## Installation
```bash
# Clone the repository
git clone https://github.com/your-repo/your-project.git
cd your-project
# Create a virtual environment
python -m venv venv
# Activate (Windows)
venv\Scripts\activate
# Activate (Unix/macOS)
source venv/bin/activate
# Install dependencies
pip install -r requirements.txt
```
---
## Configuration
1. **Google Drive credentials** – Place `credentials.json` (OAuth client) in the project root. The first run will prompt you to authenticate and generate `token.pickle`.
2. **OpenRouter API** – In the n8n workflow, replace the placeholder `Bearer <REDACTED>` with your actual API key.
3. **Port configuration** – By default, Flask runs on `0.0.0.0:5001`. Adjust the `app.run` call in `server.py` if a different port is required.
---
## Running the Server
```bash
# Activate the virtual environment if not already active
venv\Scripts\activate  # Windows
# Start the Flask API
python server.py
```
The API will be reachable at `http://localhost:5001`.
### API Endpoints
|
 Method 
|
 Path 
|
 Description 
|
|
--------
|
------
|
-------------
|
|
`POST`
|
`/generate`
|
 Starts a new video generation job. Expects a JSON payload (see 
*
Input JSON
*
 below). Returns 
`{ "status": "accepted", "task_id": "<uuid>" }`
. 
|
|
`GET`
|
`/status/<task_id>`
|
 Returns the current status of the task (
`queued`
, 
`processing`
, 
`completed`
, 
`failed`
). 
|
#### Input JSON (example)
```json
{
  "script": "Your story script here...",
  "prompts": "One detailed cinematic prompt per line, matching each sentence."
}
```
The `script` will be split into sentences, and each line in `prompts` must correspond to a sentence.
---
## n8n Workflow Overview
The provided `youtube agent.json` defines a visual workflow:
1. **Manual Trigger** – Starts the pipeline.
2. **HTTP Request** – Calls OpenRouter to generate a story, script, and image prompts.
3. **JavaScript Code** – Parses the response into `title`, `script`, and `prompts`.
4. **HTTP Request** – Sends the parsed data to the Flask `/generate` endpoint.
5. **Wait** – Pauses for a configurable period (default 1 minute).
6. **HTTP Request** – Polls the `/status/<task_id>` endpoint.
7. **If** – Checks if the status is `completed`.
8. **Google Drive Search** – Locates the final video file.
9. **Google Drive Download** – Retrieves the video.
10. **YouTube Upload** – Publishes the video to the specified channel.
The workflow can be imported directly into n8n via **Import > Workflow** and selecting the JSON file.
---
## Screenshots
Replace the placeholders below with actual screenshots of your UI, workflow, or generated video.
![Architecture Diagram](assets/architecture.png)
![n8n Workflow Screenshot](assets/n8n_workflow.png)
![Sample Generated Video](assets/sample_video.png)
---
## Cleanup & Logs
- Temporary images (`image_*.png`) and audio files (`audio_*.mp3`) are automatically deleted after video creation.
- The input JSON is removed once the job completes.
- Detailed logs are printed to the console for debugging.
---
## License
This project is licensed under the **MIT License**. See the `LICENSE` file for full terms.
---
## Contributing
Contributions are welcome! Please follow these steps:
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/your-feature`).
3. Make your changes and ensure the code passes linting and tests.
4. Open a Pull Request with a clear description of the changes.
---
## Contact
For questions or support, please open an issue on the repository or contact the maintainer at `pavan@example.com`.
