# ONE App — Complete Documentation

> **ONE** — One app to rule them all. A self-hosted, password-protected multi-tool web application built with Python and Flask.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [How It Works — Architecture](#2-how-it-works--architecture)
3. [File Structure Explained](#3-file-structure-explained)
4. [Every Feature Explained](#4-every-feature-explained)
5. [API Reference](#5-api-reference)
6. [Environment Variables (.env)](#6-environment-variables-env)
7. [Running Locally](#7-running-locally)
8. [Deployment on Hugging Face Spaces](#8-deployment-on-hugging-face-spaces)
9. [How to Edit the App](#9-how-to-edit-the-app)
10. [Troubleshooting Every Scenario](#10-troubleshooting-every-scenario)
11. [Security Reference](#11-security-reference)
12. [Pushing Updates to Live App](#12-pushing-updates-to-live-app)

---

## 1. Project Overview

**ONE** is a web application that combines multiple utility tools into one password-protected interface. It is written in Python using the Flask web framework and is deployed as a Docker container.

### What it does
| Tool | What it does |
|---|---|
| 🎵 YouTube MP3 Downloader | Downloads a single YouTube video as an MP3 audio file |
| 📋 YouTube Playlist Downloader | Downloads an entire YouTube playlist as separate MP3 files with embedded thumbnails |
| 🗜️ File Compressor | Compresses images (JPG, PNG, WebP) and PDFs to a target file size in KB |
| 🔍 AI Image Upscaler | Upscales low-resolution images to print quality (A4, A5, Poster, Wallpaper) using AI (FSRCNN model) |

### Technology Stack
| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Web Framework | Flask |
| Production Server | Gunicorn |
| Containerisation | Docker |
| AI Upscaling Model | FSRCNN (via OpenCV DNN Super Resolution) |
| Audio Processing | FFmpeg + yt-dlp |
| PDF Processing | PyMuPDF (fitz) |
| Image Processing | Pillow + OpenCV |
| Audio Metadata | Mutagen |
| Config/Secrets | python-dotenv |

---

## 2. How It Works — Architecture

```
User's Browser
      │
      │  HTTPS request to https://noelllllll-theone.hf.space
      ▼
Hugging Face Spaces (Docker Container)
      │
      │  Runs: gunicorn --bind 0.0.0.0:7860 app:app
      ▼
Flask Application (app.py)
      │
      ├── require_login()     ← Checks username + password BEFORE every request
      │
      ├── GET /               ← Serves the HTML frontend (templates/index.html)
      │
      ├── POST /api/download-mp3        ← Downloads single YouTube track
      ├── POST /api/start-playlist      ← Starts playlist download in background thread
      ├── GET  /api/playlist-progress/  ← Streams real-time progress to browser (SSE)
      ├── GET  /playlist-files/         ← Renders download page for completed playlist
      ├── GET  /api/playlist-dl/        ← Serves individual track file for download
      ├── GET  /api/playlist-zip/       ← Builds and serves ZIP of all tracks
      ├── POST /api/compress            ← Compresses uploaded file
      ├── POST /api/upscale             ← Upscales uploaded image using FSRCNN AI model
      └── GET  /api/download            ← Serves processed file back to browser
```

### Request Lifecycle
1. User visits the URL → browser shows a login popup.
2. User enters username & password → browser caches them and sends with every future request.
3. Flask's `require_login()` runs **before every single route** and checks the credentials.
4. If correct → the actual route handler runs and returns a response.
5. If wrong → the server returns HTTP 401 and the browser shows the login popup again.

---

## 3. File Structure Explained

```
d:\The App\ONE\
│
├── app.py                  ← Main application logic (all routes, all features)
├── requirements.txt        ← Python library dependencies
├── Dockerfile              ← Docker build instructions for deployment
├── Procfile                ← Heroku-style process definition (used by Gunicorn)
├── README.md               ← Hugging Face Space configuration header
├── .env                    ← Local secret keys (NEVER committed to Git)
├── .gitignore              ← Tells Git what files to never track/upload
├── .dockerignore           ← Tells Docker what files to ignore when building image
├── start.bat               ← Windows shortcut to run the app locally
├── create_shortcut.ps1     ← PowerShell script to create a desktop shortcut
│
├── templates/
│   └── index.html          ← The entire frontend UI (single HTML file)
│
└── downloads/              ← Temporary storage for all processed files
    └── FSRCNN_x4.pb        ← AI upscaling model (auto-downloaded on first run)
```

### What each important file does

#### `app.py` — The Brain
This is the entire backend. It:
- Starts the Flask web server
- Enforces password authentication on every request
- Handles all 10+ API endpoints
- Manages background threads for playlist downloads
- Communicates real-time progress to the browser via Server-Sent Events (SSE)

#### `templates/index.html` — The Face
This is the entire frontend. It:
- Contains all the HTML, CSS, and JavaScript in one file
- Sends requests to the Python backend via `fetch()` API calls
- Displays results and triggers file downloads

#### `requirements.txt` — The Shopping List
```
flask           - Web framework
yt-dlp          - YouTube downloader engine
pillow          - Image processing
pymupdf         - PDF processing
opencv-contrib-python - AI upscaling (FSRCNN model)
requests        - HTTP client (for downloading the AI model)
python-dotenv   - Reads .env file for secrets
mutagen         - Reads/writes MP3 metadata tags
gunicorn        - Production-grade web server (used in deployment)
```

#### `Dockerfile` — The Deployment Blueprint
Tells the hosting platform:
1. Use Python 3.11
2. Install system tools: `ffmpeg` (audio conversion), `libgl1` (OpenCV), etc.
3. Install Python packages from `requirements.txt`
4. Copy all app files into the container
5. Start the app with Gunicorn

#### `.env` — Your Secrets (Local Only)
This file is on your computer only and is **never** uploaded to GitHub or Hugging Face.
```
APP_USERNAME=admin
APP_PASSWORD=admin123
```
On Hugging Face, these are stored as **Secrets** in the Space settings.

#### `.gitignore` — The Privacy Guard
Tells Git to never track or upload these paths:
```
venv/           - Python virtual environment (huge, not needed)
__pycache__/    - Python compiled cache files
.env            - Your secret keys
downloads/      - Temporary processed files
*.pyc           - Python bytecode
```

---

## 4. Every Feature Explained

### 🎵 YouTube MP3 Downloader
- **Input:** A YouTube video URL
- **Process:** `yt-dlp` downloads the best available audio stream, then FFmpeg converts it to MP3 at 192kbps quality
- **Output:** An MP3 file that automatically downloads in the browser
- **File naming:** UUID prefix is stripped before download so the user gets a clean filename

### 📋 YouTube Playlist Downloader
- **Input:** A YouTube playlist URL
- **Process:**
  1. A background thread is started immediately (so the browser doesn't time out)
  2. Each track is downloaded and converted to MP3 with embedded album art (thumbnail)
  3. Tracks are numbered: `01. Song Name.mp3`, `02. Song Name.mp3` etc.
  4. Progress is streamed to the browser in real-time using Server-Sent Events
- **Output:** A dedicated page showing all tracks with individual download buttons + a "Download All as ZIP" button
- **Important:** Downloaded playlist files are stored in memory only. If the server restarts, the download page links will no longer work. Users must re-download.

### 🗜️ File Compressor
- **Supported formats:** JPG/JPEG, PNG, WebP, PDF, and any other file (compressed to ZIP)
- **Input:** A file + a target size in KB
- **Process for images (JPG):** Uses a binary search algorithm to find the optimal JPEG quality setting that results in a file closest to (but not exceeding) the target size
- **Process for PNG:** Uses lossless optimization only (PNG cannot be compressed lossy without losing transparency)
- **Process for PDF:** Progressively reduces DPI (from 150 down to 30) until the file fits the target size
- **Process for other files:** Wraps the file in a ZIP archive
- **Output:** The compressed file, downloaded automatically

### 🔍 AI Image Upscaler
- **Input:** An image (JPG, PNG, WebP) + target format (A4, A5, Poster, Wallpaper) + orientation
- **AI Model:** FSRCNN (Fast Super Resolution Convolutional Neural Network) — a deep learning model specifically trained for image super-resolution. The `.pb` file is the trained model weights
- **Process:**
  1. On first startup, the model is automatically downloaded from GitHub (~1MB)
  2. The image is optionally denoised using OpenCV's non-local means denoising
  3. The FSRCNN model upscales the image by 4x (applied repeatedly if more is needed)
  4. Contrast and brightness are adjusted (10% contrast boost by default)
  5. The image is resized to exactly match the target dimensions using Lanczos resampling
  6. Center-cropped to fit the canvas perfectly
  7. An unsharp mask (sharpening filter) is applied for crisp output
- **Output sizes:**
  | Format | Portrait | Landscape |
  |---|---|---|
  | A4 | 2480 × 3508 px | 3508 × 2480 px |
  | A5 | 1748 × 2480 px | 2480 × 1748 px |
  | Poster | 2480 × 3508 px | 3508 × 2480 px |
  | Wallpaper | 2160 × 3840 px | 3840 × 2160 px |

---

## 5. API Reference

All endpoints require HTTP Basic Authentication.

| Method | Endpoint | Description | Body |
|---|---|---|---|
| `GET` | `/` | Serves the main UI | — |
| `POST` | `/api/download-mp3` | Download single YouTube MP3 | `{"url": "..."}` |
| `POST` | `/api/start-playlist` | Start playlist download | `{"url": "..."}` |
| `GET` | `/api/playlist-progress/<task_id>` | Stream progress (SSE) | — |
| `GET` | `/playlist-files/<task_id>` | Playlist file browser page | — |
| `GET` | `/api/playlist-dl/<task_id>/<filename>` | Download single playlist track | — |
| `GET` | `/api/playlist-zip/<task_id>` | Download all tracks as ZIP | — |
| `POST` | `/api/compress` | Compress a file | `multipart/form-data` with `file` + `target_kb` |
| `POST` | `/api/upscale` | Upscale an image | `multipart/form-data` with `file` + `format` + `orientation` |
| `GET` | `/api/download?file=<filename>` | Download a processed file | — |

---

## 6. Environment Variables (.env)

### Local `.env` file (at `d:\The App\ONE\.env`)

| Variable | Default | Description |
|---|---|---|
| `APP_USERNAME` | `admin` | Login username for the app |
| `APP_PASSWORD` | `admin123` | Login password for the app |

### How to change the password (Local)
1. Open `d:\The App\ONE\.env` in any text editor
2. Change `APP_PASSWORD=admin123` to your new password
3. Save the file and restart the app

### How to change the password (Hugging Face)
1. Go to your Space → **Settings** tab
2. Scroll to **Variables and secrets**
3. Find `APP_PASSWORD` → click Edit → type new password → Save
4. The app restarts automatically

---

## 7. Running Locally

### Prerequisites
- Python 3.11+
- FFmpeg installed and on PATH ([Download here](https://ffmpeg.org/download.html))
- Git

### First-time setup
```powershell
# Navigate to the app folder
cd "D:\The App\ONE"

# Create a virtual environment
python -m venv venv

# Activate it
.\venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

### After first-time setup (daily use)
Just double-click `start.bat` — it does all of the above automatically.

### Accessing the app
Open your browser and go to: `http://localhost:5000`

---

## 8. Deployment on Hugging Face Spaces

### Live URL
```
https://noelllllll-theone.hf.space
```

### How deployment works
1. You push code to your Hugging Face Space git remote.
2. Hugging Face detects the `Dockerfile` and automatically builds a Docker image.
3. The Docker image is run as a container, which starts Gunicorn on the internal port.
4. Hugging Face proxies all traffic from the public URL to this container.

> [!IMPORTANT]
> **Secrets are NOT in the code.** All API keys and passwords are stored in the Space's "Secrets" settings, not in any file. This is what keeps your keys secure even though the code is "public".

### Space Settings
- **Space URL:** https://huggingface.co/spaces/noelllllll/TheOne
- **SDK:** Docker
- **Port:** Automatically handled by Hugging Face

### Secrets to add in Space Settings

| Secret Name | Value |
|---|---|
| `APP_USERNAME` | `admin` |
| `APP_PASSWORD` | Your chosen password |
| `GEMINI_API_KEY` | From your `.env` file |
| `GEMINI_API_KEY_2` | From your `.env` file |
| ... | ... |
| `GEMINI_API_KEY_10` | From your `.env` file |

> [!NOTE]
> The Gemini API keys are for the AI image upscaler's "Gemini guidance" feature. The app will still work without them — it just falls back to local defaults for image processing parameters.

---

## 9. How to Edit the App

### Editing the UI (what users see)
**File to edit:** `d:\The App\ONE\templates\index.html`

This is a single HTML file containing all the CSS styles, HTML layout, and JavaScript logic. Open it in VS Code and edit directly.

### Editing the Backend (how things work)
**File to edit:** `d:\The App\ONE\app.py`

Key locations inside `app.py`:

| Line range | What it does |
|---|---|
| Lines 1–29 | Imports and setup |
| Lines 30–43 | Password authentication setup |
| Lines 52–62 | AI model auto-download logic |
| Lines 70–76 | Main page route |
| Lines 78–113 | YouTube single MP3 download |
| Lines 115–205 | YouTube playlist download (worker + progress + file browser) |
| Lines 395–472 | File compression logic |
| Lines 474–579 | AI image upscaling logic |

### Adding a new feature
1. Add the new route/function in `app.py`
2. Add the UI button/section in `templates/index.html`
3. Add any new required libraries to `requirements.txt`
4. Test locally with `python app.py`
5. Deploy by pushing to Hugging Face (see Section 12)

### Changing the app name or branding
- **Title in browser tab:** Edit the `<title>` tag in `templates/index.html`
- **App name on Hugging Face:** Edit `README.md` (change `title: TheOne`)
- **Emoji on Hugging Face:** Edit `README.md` (change `emoji: 🚀`)

---

## 10. Troubleshooting Every Scenario

### The app won't start locally
**Symptom:** Running `python app.py` gives an error.

| Error message | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'flask'` | Run `pip install -r requirements.txt` |
| `ModuleNotFoundError: No module named 'cv2'` | Run `pip install opencv-contrib-python` |
| `FileNotFoundError: ffmpeg not found` | Install FFmpeg and add it to your system PATH |
| `Port 5000 already in use` | Close other apps using port 5000, or change port in `app.py` line 587 |

---

### The Hugging Face app shows "Building" for a long time
**Normal build time:** 3–8 minutes (Docker has to install FFmpeg, OpenCV, etc.)
If it is stuck for more than 15 minutes:
1. Go to the **Logs** tab on your Space page.
2. Read the error at the bottom.
3. If it says a package failed to install, it may be a network issue. Click **Factory restart** in the Settings tab.

---

### The Hugging Face app shows "Error" / "Stopped"
1. Go to the **Logs** tab.
2. Look for `ERROR` or `Exception` lines.
3. Common causes:
   - A missing secret → add the missing environment variable in Settings → Secrets
   - A Python crash → read the traceback and fix the bug in `app.py`
4. After fixing, click **Restart this Space** in the Settings tab.

---

### Login popup keeps appearing / can't log in
**On your browser:**
- Make sure **Caps Lock is OFF**.
- The default username is `admin` and password is `admin123`.
- If you changed the password in Secrets but it still doesn't work, try a Private/Incognito window (your browser may have cached the old password).
- To force your browser to forget the cached credentials: clear your browser's saved passwords for the site.

**If you forgot the password:**
1. Go to Hugging Face Space → Settings → Secrets
2. Find `APP_PASSWORD` and change it to something you know
3. The Space restarts automatically

---

### YouTube download fails
| Error | Cause | Fix |
|---|---|---|
| `Video unavailable` | The video is private, deleted, or region-blocked | Use a different video |
| `Sign in to confirm your age` | Age-restricted video | yt-dlp may not handle this without cookies |
| `HTTP Error 429: Too Many Requests` | YouTube is rate-limiting the server's IP | Wait 10–30 minutes and try again |
| `ffmpeg not found` | FFmpeg not installed in the container | Rebuild the Docker image (it should install automatically) |

---

### Downloaded files are lost after server restart
**This is by design.** The `downloads/` folder is inside the container and is not persistent on Hugging Face free tier. All processed files are gone when the container restarts. Users must re-process their files each session.

**To make files persistent (advanced):** You would need to mount an external storage volume, which is not available on the free Hugging Face tier.

---

### The AI upscaler is very slow
This is expected on free hosting. The FSRCNN model runs on CPU (no GPU on free tier). Processing times:
- Small image (< 1 MP): ~10–20 seconds
- Medium image (1–4 MP): ~30–90 seconds
- Large image (> 4 MP): ~2–5 minutes

If it times out: the default timeout is 120 seconds (set in `Procfile` and `Dockerfile`). For very large images, this may not be enough. You can increase it by editing the `--timeout 120` value.

---

### File compression result is larger than the target
- For **PNG files**: PNG is lossless and cannot be compressed below a certain threshold without losing transparency. This is a known limitation. Convert to JPG for better compression.
- For **PDF files**: If every page is already a low-quality image, there is a floor below which it cannot go.

---

### App says "No Gemini API keys configured"
This only affects the AI Image Upscaler's "Gemini guidance" feature. The app still works:
- Add your `GEMINI_API_KEY` to the Space Secrets (or `.env` locally)
- The app will use local default enhancement parameters if no key is present

---

### Hugging Face Space goes to sleep
Free Hugging Face Spaces pause after **48 hours of inactivity**. When someone visits the URL, it wakes up in about 30–60 seconds automatically.

**To prevent sleeping:** Use [UptimeRobot](https://uptimerobot.com/) — set up a free monitor that pings your URL every 20 minutes. This keeps the Space awake indefinitely.

---

### App is working but downloads aren't starting
This is usually a browser issue, not a server issue:
- Check if your browser is **blocking pop-ups or downloads** from the site
- Try in a different browser (Chrome works best)
- Check if your browser's download folder is full or write-protected

---

## 11. Security Reference

### What is protected
- ✅ Every single page and API endpoint is protected by the password
- ✅ API keys are stored as Secrets (not in code)
- ✅ `.env` file is in `.gitignore` (never uploaded to GitHub)
- ✅ File paths are sanitized to prevent directory traversal attacks
- ✅ Filenames are stripped of dangerous characters (`/ \ * ? : " < > |`)

### What is NOT protected (known limitations)
- ⚠️ Basic Auth sends credentials in Base64 encoding. On HTTP (not HTTPS), these can be intercepted. Hugging Face serves over HTTPS automatically, so this is not an issue in production.
- ⚠️ There is no rate limiting on the login. Someone could theoretically brute-force the password. Use a strong password.
- ⚠️ Downloaded files are stored on the server temporarily. Anyone who knows the exact UUID filename can download them without a password (the `/api/download?file=` endpoint checks for file existence, not auth — actually, auth IS enforced on all routes via `require_login`).

### To change the password
1. **Locally:** Edit `.env` → change `APP_PASSWORD` → restart app
2. **Hugging Face:** Settings → Secrets → Edit `APP_PASSWORD` → Space restarts automatically

---

## 12. Pushing Updates to Live App

### Workflow for making changes

```
1. Edit files locally in D:\The App\ONE\
2. Test locally by running python app.py
3. Push to Hugging Face to go live
```

### Step-by-step push commands
```powershell
# Navigate to the app folder
cd "D:\The App\ONE"

# Stage all changed files
git add .

# Save the changes with a description
git commit -m "Brief description of what you changed"

# Push to Hugging Face (makes changes live in ~3 minutes)
git push huggingface main
```

### To also push to GitHub (backup)
```powershell
git push origin main
```

### Quick reference for common edits

| What you want to change | File to edit | Command after saving |
|---|---|---|
| UI design / layout | `templates/index.html` | `git add . && git commit -m "UI update" && git push huggingface main` |
| Add a new tool/feature | `app.py` + `index.html` | Same as above |
| Change the password | Hugging Face Space Settings → Secrets | No push needed |
| Add a new Python library | `requirements.txt` | Push triggers a full Docker rebuild |
| Change timeout/workers | `Procfile` or `Dockerfile` | Push triggers a full Docker rebuild |

> [!WARNING]
> After pushing changes to `requirements.txt` or `Dockerfile`, Hugging Face will do a **full rebuild** which can take 5–10 minutes. Your app will be unavailable during this time.

> [!TIP]
> Changes to `app.py` and `templates/index.html` only trigger a **fast restart** (about 30 seconds). Make all your non-dependency changes in these files to minimise downtime.

---

*Documentation generated for ONE App — June 2026*
