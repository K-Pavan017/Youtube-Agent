import os
import time
import asyncio
import json
import edge_tts  # pyrefly: ignore [missing-import]
import aiohttp    # pyrefly: ignore [missing-import]
import re
import pickle
import sys
import io
import urllib.parse
import random
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips, vfx  # pyrefly: ignore [missing-import]
from googleapiclient.discovery import build       # pyrefly: ignore [missing-import]
from googleapiclient.http import MediaFileUpload      # pyrefly: ignore [missing-import]
from google_auth_oauthlib.flow import InstalledAppFlow       # pyrefly: ignore [missing-import]
from google.auth.transport.requests import Request          # pyrefly: ignore [missing-import]
from PIL import Image       # pyrefly: ignore [missing-import]

# ---------------- CONFIG ----------------
# Use absolute path to the directory where tts.py lives
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
INPUT_JSON = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_PATH, "input.json")
OUTPUT_VIDEO = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE_PATH, "output.mp4")
FPS = 24
IMAGE_SIZE = (1280, 720) 
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Force unbuffered stdout for real-time Flask logs
sys.stdout.reconfigure(line_buffering=True)

# ---------------- DATA PREPARATION ----------------
def load_input_data():
    abs_input_path = os.path.abspath(INPUT_JSON)
    print(f"--- [DEBUG] Reading JSON: {abs_input_path}", flush=True)
    
    # Robust wait for the input file (up to 30 seconds)
    max_retries = 15
    for i in range(max_retries):
        if os.path.exists(abs_input_path) and os.path.getsize(abs_input_path) > 0:
            print(f"--- [OK] Found input file: {abs_input_path}", flush=True)
            break
        print(f"[{time.strftime('%H:%M:%S')}] Waiting for input.json (Attempt {i+1}/{max_retries})...", flush=True)
        time.sleep(2)

    if not os.path.exists(abs_input_path):
        print(f"CRITICAL ERROR: File {abs_input_path} not found or is empty after waiting.", flush=True)
        sys.exit(1)

    with open(abs_input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scenes = data.get("scenes")
    if not scenes:
        script = data.get("script", "")
        # Clean up script and split strictly by full stops
        script = script.replace("\n", " ").strip()
        sentences = [s.strip() for s in script.split('.') if len(s.strip()) > 5]
        
        # Check if we have matching prompts
        prompts_raw = data.get("prompts", "")
        prompts = [p.strip() for p in prompts_raw.split('\n') if len(p.strip()) > 5]
        
        scenes = []
        for i, text in enumerate(sentences):
            # Try to use a specific prompt if available, otherwise use the text
            raw_prompt = prompts[i] if i < len(prompts) else text
            
            # Enhance prompt for cinematic quality
            enhanced_prompt = f"{raw_prompt}, cinematic, professional, 8k, highly detailed, masterpiece, photorealistic, cinematic lighting, soft shadows, sharp focus, 35mm lens, f/1.8, vibrant colors, bright atmosphere"
            scenes.append({"text": text, "prompt": enhanced_prompt})
    
    return scenes

# Strictly serial image generation to avoid 429 rate limits
image_semaphore = asyncio.Semaphore(1)

async def download_image(session, prompt, index):
    # Use a longer prompt for more detail (up to 500 chars)
    full_prompt = prompt[:500].strip()
    image_path = os.path.join(BASE_PATH, f"image_{index}.png")
    
    # Standard Browser Headers to avoid bot detection
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    
    # Models to rotate through if rate limited
    models = ["flux-anime", "flux", "flux-realism", "flux-pro", "flux-3d", "any-dark"]
    
    async with image_semaphore:
        # Use only these 3 models in rotation
        target_models = ["flux-anime", "flux-realism", "flux-3d"]
        
        for attempt in range(8): # 6 total attempts (2 per model)
            model_to_use = target_models[attempt % len(target_models)]
            seed = random.randint(1, 1000000)
            
            params = {
                "width": IMAGE_SIZE[0],
                "height": IMAGE_SIZE[1],
                "nologo": "true",
                "seed": seed,
                "model": model_to_use
            }
            
            # Use proper URL encoding for the prompt
            encoded_prompt = urllib.parse.quote(full_prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            
            print(f"  [IMAGE] Scene {index}: Downloading (Attempt {attempt+1}, Model: {model_to_use})...", flush=True)
            try:
                async with session.get(url, params=params, headers=headers, timeout=60, ssl=False) as response:
                    if response.status == 200:
                        content = await response.read()
                        if len(content) > 5000: 
                            img = Image.open(io.BytesIO(content)).resize(IMAGE_SIZE)
                            img.save(image_path)
                            print(f"  [IMAGE] Scene {index}: Saved [OK]", flush=True)
                            return image_path
                    elif response.status == 429:
                        wait_time = (attempt + 1) * 10
                        print(f"  [IMAGE] Scene {index}: API Busy (429). Waiting {wait_time}s...", flush=True)
                        await asyncio.sleep(wait_time)
            except Exception:
                pass
            await asyncio.sleep(3) 
            
    # FALLBACK: Create a black image if all retries fail
    print(f"  [IMAGE] Scene {index}: ALL RETRIES FAILED. Creating black fallback image.", flush=True)
    try:
        black_img = Image.new('RGB', IMAGE_SIZE, color='black')
        black_img.save(image_path)
        return image_path
    except Exception as e:
        print(f"  [IMAGE] Scene {index}: Fallback failed -> {e}", flush=True)
        return None

async def generate_audio(text, index):
    audio_path = os.path.join(BASE_PATH, f"audio_{index}.mp3")
    print(f"  [AUDIO] Scene {index}: Generating...", flush=True)
    try:
        communicate = edge_tts.Communicate(text, "en-US-AriaNeural")
        await communicate.save(audio_path)
        print(f"  [AUDIO] Scene {index}: Saved [OK]", flush=True)
        return audio_path
    except Exception as e:
        print(f"  [AUDIO] Scene {index}: FAILED [FAIL] -> {e}", flush=True)
    return None

async def process_scene(session, scene, i):
    text = scene.get("text", "")
    prompt = scene.get("prompt", scene.get("image_prompt", text)) # fallback to text if no prompt
    
    # Ensure even JSON-provided prompts get enhanced if they are too short
    if len(prompt) < 100 and "cinematic" not in prompt.lower():
        prompt = f"A professional cinematic scene of {prompt}, 8k resolution, highly detailed, photorealistic, masterpiece, vibrant colors, bright studio lighting, sharp focus, high contrast, cinematic atmosphere"
    elif "cinematic" not in prompt.lower():
        prompt += ", cinematic, professional, 8k, photorealistic, vibrant colors, well-lit"

    print(f"  [SCENE] Scene {i}: Starting generation. Text: '{text[:40]}...' | Prompt: '{prompt[:40]}...'", flush=True)
    
    # Launch both at once
    audio_task = generate_audio(text, i)
    image_task = download_image(session, prompt, i)
    
    audio_path, image_path = await asyncio.gather(audio_task, image_task)
    
    if audio_path and image_path:
        try:
            audio_clip = AudioFileClip(audio_path)
            # Create the clip with a Ken Burns (Zoom) effect
            img_clip = ImageClip(image_path).with_duration(max(audio_clip.duration, 0.5))
            
            # Subtly zoom in over time to create animation (Ken Burns effect)
            # MoviePy 2.x uses .resized(lambda t: ...) for dynamic resizing
            clip = (img_clip
                    .resized(lambda t: 1 + 0.1 * (t / img_clip.duration))
                    .with_position("center")
                    .resized(IMAGE_SIZE) # Ensure final size is correct after zoom
                    .with_effects([vfx.FadeIn(0.5), vfx.FadeOut(0.5)])
                    .with_audio(audio_clip))
            
            print(f"  [SCENE] Scene {i}: Animated [DONE]", flush=True)
            return (i, clip, audio_path, image_path) # Include index for sorting
        except Exception as e:
            print(f"  [ERR] Scene {i}: Assembly error -> {e}", flush=True)
    return None

# ---------------- GOOGLE DRIVE & HELPERS ----------------
def upload_to_drive(file_path, file_name):
    token_path = os.path.join(BASE_PATH, 'token.pickle')
    creds_path = os.path.join(BASE_PATH, 'credentials.json')
    creds = None

    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)

    service = build('drive', 'v3', credentials=creds)
    results = service.files().list(q=f"name='{file_name}' and trashed=false", fields='files(id, name)').execute()
    files = results.get('files', [])
    media = MediaFileUpload(file_path, resumable=True)

    if files:
        file_id = files[0]['id']
        service.files().update(fileId=file_id, media_body=media).execute()
        print(f"[{time.strftime('%H:%M:%S')}] Drive: Updated Video.", flush=True)
    else:
        file_metadata = {'name': file_name}
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"[{time.strftime('%H:%M:%S')}] Drive: Uploaded New Video.", flush=True)

# ---------------- VIDEO CREATION ----------------
def create_video(scene_data):
    # Sort by the index (first element of the tuple) to keep story order
    scene_data.sort(key=lambda x: x[0])
    
    video_clips = [data[1] for data in scene_data]
    all_temp_files = []
    for data in scene_data:
        all_temp_files.extend([data[2], data[3]])

    print(f"\n[{time.strftime('%H:%M:%S')}] MoviePy: Stitching {len(video_clips)} clips...", flush=True)
    final_video = concatenate_videoclips(video_clips, method="compose")
    
    print(f"[{time.strftime('%H:%M:%S')}] Rendering MP4...", flush=True)
    final_video.write_videofile(
        OUTPUT_VIDEO,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        logger=None # Suppress internal moviepy logs to keep terminal clean
    )
    
    upload_to_drive(OUTPUT_VIDEO, "final_video.mp4")
    
    # Give Drive a few seconds to index the file so n8n search finds it
    print(f"[{time.strftime('%H:%M:%S')}] Drive: Waiting for propagation...", flush=True)
    time.sleep(5)
    
    print(f"[{time.strftime('%H:%M:%S')}] Cleanup: Removing local video...", flush=True)
    if os.path.exists(OUTPUT_VIDEO):
        os.remove(OUTPUT_VIDEO)


# ---------------- RUN ----------------
async def main():
    print(f"--- Workflow Started: {time.strftime('%H:%M:%S')} ---", flush=True)
    try:
        scenes = load_input_data()
        print(f"Generating {len(scenes)} scenes sequentially...", flush=True)
        
        results = []
        async with aiohttp.ClientSession() as session:
            for i, scene in enumerate(scenes):
                print(f"\n--- [PROGRESS] Processing Scene {i+1} of {len(scenes)} ---", flush=True)
                result = await process_scene(session, scene, i)
                results.append(result)
        
        valid_results = [r for r in results if r is not None]
        
        if valid_results:
            create_video(valid_results)
            
            # Print detailed summary
            print("\n" + "="*40)
            print("       🎥 FINAL GENERATION SUMMARY")
            print("="*40)
            print(f"Total Scenes Processed: {len(valid_results)}")
            
            print("\n📸 Images Generated:")
            for r in valid_results:
                print(f"  - {os.path.basename(r[3])}")
                
            print("\n🔊 Audio Files Generated:")
            for r in valid_results:
                print(f"  - {os.path.basename(r[2])}")
                
            print(f"\n🎬 Final Video Created and Uploaded: final_video.mp4")
            print("="*40 + "\n")
            
            print(f"--- Workflow Completed: {time.strftime('%H:%M:%S')} ---", flush=True)
        else:
            print("CRITICAL ERROR: No clips generated.", flush=True)
    except Exception as e:
        print(f"CRITICAL ERROR in Workflow: {e}", flush=True)
    finally:
        # Aggressive cleanup of all temporary files
        print(f"[{time.strftime('%H:%M:%S')}] Performing final cleanup...", flush=True)
        for f in os.listdir(BASE_PATH):
            if f.startswith("image_") and f.endswith(".png"):
                try: os.remove(os.path.join(BASE_PATH, f))
                except: pass
            if f.startswith("audio_") and f.endswith(".mp3"):
                try: os.remove(os.path.join(BASE_PATH, f))
                except: pass
        if os.path.exists(OUTPUT_VIDEO):
            try: os.remove(OUTPUT_VIDEO)
            except: pass

        # The final act: delete the input file only after everything else is done
        if os.path.exists(INPUT_JSON):
            try: 
                os.remove(INPUT_JSON)
                print(f"[{time.strftime('%H:%M:%S')}] Workflow complete. Deleted input file: {INPUT_JSON}", flush=True)
            except: pass

        print(f"[{time.strftime('%H:%M:%S')}] Cleanup Complete.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())