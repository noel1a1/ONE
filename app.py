import os
import io
import time
import uuid
import queue
import zipfile
import threading
import re
import json
import ssl
from flask import Flask, request, send_file, render_template, Response, jsonify, make_response
import yt_dlp
from PIL import Image, ImageFilter
import fitz  # PyMuPDF
import cv2
import numpy as np
import requests
from dotenv import load_dotenv
import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TYER, TCON

# ── Global SSL patch ──────────────────────────────────────────────────────────
# Fixes "EOF unexpected while reading in violation of protocol" errors that
# yt-dlp encounters on networks with strict TLS filtering or legacy servers.
try:
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE
    # Allow legacy renegotiation (needed on some ISPs / corporate proxies)
    _ssl_ctx.options |= getattr(ssl, 'OP_LEGACY_SERVER_CONNECT', 0)
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass  # If ssl patching fails, continue without it

# Load environment variables
load_dotenv()

# ONE — one app to rule them all
# pip install -r requirements.txt
# python app.py
# Open http://localhost:5000

app = Flask(__name__)

# Basic Authentication Configuration
APP_USERNAME = os.environ.get('APP_USERNAME', 'admin')
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'admin123')

@app.before_request
def require_login():
    auth = request.authorization
    if not auth or auth.username != APP_USERNAME or auth.password != APP_PASSWORD:
        return Response(
            'Login Required', 401,
            {'WWW-Authenticate': 'Basic realm="Login Required"'}
        )

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), 'downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MODEL_URL = "https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/FSRCNN_x4.pb"
MODEL_PATH = os.path.join(DOWNLOAD_DIR, "FSRCNN_x4.pb")


def ensure_model_exists():
    if not os.path.exists(MODEL_PATH):
        print("Downloading FSRCNN_x4.pb model for AI Upscaling...")
        response = requests.get(MODEL_URL, stream=True)
        response.raise_for_status()
        with open(MODEL_PATH, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("Model downloaded successfully.")

ensure_model_exists()

# Progress tracking for playlists
# task_id -> queue.Queue
progress_queues = {}
# Stores completed playlist dirs: task_id -> (playlist_dir, playlist_title)
completed_playlists = {}

@app.route('/')
def index():
    response = make_response(render_template('index.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/download-mp3', methods=['POST'])
def download_mp3():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    task_id = str(uuid.uuid4())
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(DOWNLOAD_DIR, f'{task_id}_%(title)s.%(ext)s'),
        'quiet': True,
        'nocheckcertificate': True,
        'legacy_server_connect': True,
        'socket_timeout': 30,
        'retries': 5,
        'fragment_retries': 5,
        'http_chunk_size': 10485760,
    }

    cookiefile = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
    if os.path.exists(cookiefile) and os.path.getsize(cookiefile) > 0:
        ydl_opts['cookiefile'] = cookiefile

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'audio')
            
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(task_id) and f.endswith('.mp3'):
                    safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip().replace(" ", "_")
                    if not safe_title:
                        safe_title = "audio"
                    new_filename = f"{task_id}_{safe_title}.mp3"
                    os.rename(os.path.join(DOWNLOAD_DIR, f), os.path.join(DOWNLOAD_DIR, new_filename))
                    return jsonify({"filename": new_filename})
            return jsonify({"error": "File not found after download"}), 500
    except Exception as e:
        # Produce a concise, human-readable error instead of the full yt-dlp traceback
        err_str = str(e)
        if 'SSL' in err_str or 'EOF' in err_str:
            friendly = 'SSL/Network error — YouTube blocked the connection. Try: configure YouTube cookies in the Cookies menu, disable VPN/proxy, or switch networks.'
        elif 'Unsupported URL' in err_str or 'is not a valid URL' in err_str:
            friendly = 'Invalid URL — paste a full YouTube video link.'
        elif 'Sign in' in err_str or 'age' in err_str.lower():
            friendly = 'Age-restricted video or bot block — configure cookies to bypass.'
        elif 'Private' in err_str or 'not available' in err_str:
            friendly = 'Video is private or unavailable.'
        else:
            # Trim long yt-dlp error prefixes like "[youtube] XXXX: ..."
            friendly = re.sub(r'^\[.*?\]\s*[\w-]+:\s*', '', err_str, flags=re.DOTALL).strip()[:200]
        return jsonify({"error": friendly}), 500

def playlist_download_worker(task_id, url):
    playlist_dir = os.path.join(DOWNLOAD_DIR, task_id)
    os.makedirs(playlist_dir, exist_ok=True)
    
    q = progress_queues.get(task_id)
    
    def progress_hook(d):
        if d['status'] == 'finished':
            # This triggers when a track finishes downloading, but before post-processing
            # yt-dlp might change the extension later, but we just want the track name
            filename = d.get('filename', '')
            title = os.path.splitext(os.path.basename(filename))[0]
            if q:
                q.put(f"data: {title}\n\n")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            },
            {
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            },
            {
                'key': 'EmbedThumbnail',
                'already_have_thumbnail': False,
            }
        ],
        'writethumbnail': True,
        'outtmpl': os.path.join(playlist_dir, '%(playlist_index)02d. %(title)s.%(ext)s'),
        'quiet': True,
        'progress_hooks': [progress_hook],
        'ignoreerrors': True,
        'nocheckcertificate': True,
        'legacy_server_connect': True,
        'socket_timeout': 30,
        'retries': 5,
        'fragment_retries': 5,
        'http_chunk_size': 10485760,
    }

    cookiefile = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
    if os.path.exists(cookiefile) and os.path.getsize(cookiefile) > 0:
        ydl_opts['cookiefile'] = cookiefile

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
        title = "playlist"
        if info:
            title = info.get('title') or info.get('playlist_title') or 'playlist'
            
        safe_title = re.sub(r'[\\/*?":/<>|]', "", title).strip()
        if not safe_title:
            safe_title = "playlist"

        # Check if we actually downloaded any mp3 files
        mp3_files = [f for f in os.listdir(playlist_dir) if f.lower().endswith('.mp3')]
        if not mp3_files:
            raise Exception("No tracks were successfully downloaded. YouTube blocked the connection or the URL is invalid. Configure cookies in the Cookies menu to bypass.")

        # Store completed playlist dir for mobile file browser
        completed_playlists[task_id] = (playlist_dir, safe_title)
            
        if q:
            q.put(f"data: DONE|{task_id}\n\n")
            
    except Exception as e:
        if q:
            try:
                import shutil
                shutil.rmtree(playlist_dir)
            except Exception:
                pass
            q.put(f"data: ERROR|{str(e)}\n\n")

@app.route('/api/save-cookies', methods=['POST'])
def save_cookies():
    data = request.json
    cookies_text = data.get('cookies_text', '')
    
    cookiefile = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
    try:
        with open(cookiefile, 'w', encoding='utf-8') as f:
            f.write(cookies_text)
        return jsonify({"success": True, "message": "Cookies saved successfully"})
    except Exception as e:
        return jsonify({"error": f"Failed to save cookies: {str(e)}"}), 500

@app.route('/api/clear-cookies', methods=['POST'])
def clear_cookies():
    cookiefile = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
    try:
        if os.path.exists(cookiefile):
            os.remove(cookiefile)
        return jsonify({"success": True, "message": "Cookies cleared successfully"})
    except Exception as e:
        return jsonify({"error": f"Failed to clear cookies: {str(e)}"}), 500

@app.route('/api/check-cookies', methods=['GET'])
def check_cookies():
    cookiefile = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
    exists = os.path.exists(cookiefile)
    size_bytes = os.path.getsize(cookiefile) if exists else 0
    content = ""
    if exists:
        try:
            with open(cookiefile, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            pass
    return jsonify({
        "exists": exists,
        "size_bytes": size_bytes,
        "content": content
    })

@app.route('/api/start-playlist', methods=['POST'])
def start_playlist():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
        
    task_id = str(uuid.uuid4())
    progress_queues[task_id] = queue.Queue()
    
    threading.Thread(target=playlist_download_worker, args=(task_id, url)).start()
    return jsonify({"task_id": task_id})

@app.route('/api/playlist-progress/<task_id>')
def playlist_progress(task_id):
    def generate():
        q = progress_queues.get(task_id)
        if not q:
            yield "data: ERROR|Invalid task ID\n\n"
            return
            
        while True:
            msg = q.get()
            yield msg
            if "DONE|" in msg or "ERROR|" in msg:
                # Cleanup queue after finishing
                del progress_queues[task_id]
                break
    return Response(generate(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache'})

@app.route('/playlist-files/<task_id>')
def playlist_files(task_id):
    """Mobile-friendly file browser page for a completed playlist download."""
    entry = completed_playlists.get(task_id)
    if not entry:
        return "<h2 style='font-family:sans-serif;padding:40px'>Playlist not found or expired. Please download again.</h2>", 404

    playlist_dir, playlist_title = entry
    if not os.path.isdir(playlist_dir):
        return "<h2 style='font-family:sans-serif;padding:40px'>Files no longer available on server.</h2>", 404

    # Collect all mp3 files, sorted by name (track number prefix sorts naturally)
    mp3_files = sorted([f for f in os.listdir(playlist_dir) if f.lower().endswith('.mp3')])
    total = len(mp3_files)

    # Build file rows
    rows_html = ""
    for i, fname in enumerate(mp3_files):
        fpath = os.path.join(playlist_dir, fname)
        size_kb = os.path.getsize(fpath) / 1024
        size_str = f"{size_kb/1024:.1f} MB" if size_kb > 1024 else f"{size_kb:.0f} KB"
        # Clean display name — strip leading "01. " style prefix for display but keep for sorting
        display = fname.rsplit('.', 1)[0]  # remove .mp3
        # Server filename is just the basename inside the task subfolder
        dl_param = fname  # we'll serve from playlist_dir below
        row_bg = "#1a1a1a" if i % 2 == 0 else "#141414"
        rows_html += f"""
        <div style="display:flex;align-items:center;gap:12px;padding:14px 16px;background:{row_bg};border-bottom:1px solid #2a2a2a;">
          <div style="font-family:'Bebas Neue',sans-serif;font-size:1.3rem;color:#F5E642;min-width:36px;text-align:center;flex-shrink:0;">{i+1}</div>
          <div style="flex:1;min-width:0;">
            <div style="font-size:0.88rem;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{display}</div>
            <div style="font-size:0.7rem;color:#888;margin-top:2px;">{size_str}</div>
          </div>
          <a href="/api/playlist-dl/{task_id}/{fname}" download="{fname}"
             style="background:#E8323A;color:#fff;font-weight:700;font-size:0.72rem;letter-spacing:1px;text-decoration:none;padding:9px 16px;border-radius:8px;white-space:nowrap;flex-shrink:0;">
            ⬇ GET
          </a>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{playlist_title} — ONE App</title>
  <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;700&display=swap" rel="stylesheet">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#0a0a0a;color:#fff;font-family:'DM Sans',sans-serif;min-height:100vh;}}
    .header{{background:linear-gradient(135deg,#E8323A,#c0222a);padding:24px 20px;}}
    .header-back{{display:inline-flex;align-items:center;gap:6px;color:#ffffff90;font-size:0.75rem;letter-spacing:1.5px;text-transform:uppercase;text-decoration:none;margin-bottom:14px;}}
    .header-title{{font-family:'Bebas Neue',sans-serif;font-size:2.2rem;line-height:1;color:#F5E642;-webkit-text-stroke:1px rgba(0,0,0,0.4);word-break:break-word;}}
    .header-sub{{font-size:0.75rem;color:#ffffff80;margin-top:6px;letter-spacing:1px;}}
    .dl-all{{display:block;margin:16px;padding:16px;background:#F5E642;color:#111;font-weight:700;font-size:0.85rem;letter-spacing:2px;text-transform:uppercase;border-radius:12px;text-align:center;text-decoration:none;border:2.5px solid #111;}}
    .dl-all:active{{opacity:0.85;}}
    .list-header{{padding:10px 16px;font-size:0.62rem;letter-spacing:3px;color:#ffffff40;text-transform:uppercase;border-bottom:1px solid #222;}}
    .file-list{{border-radius:12px;overflow:hidden;margin:0 16px 32px;border:1.5px solid #2a2a2a;}}
    @media(max-width:400px){{.header-title{{font-size:1.8rem;}}}}
  </style>
</head>
<body>
  <div class="header">
    <a href="/" class="header-back">← Back to ONE App</a>
    <div class="header-title">{playlist_title}</div>
    <div class="header-sub">{total} track{'s' if total != 1 else ''} ready to download</div>
  </div>

  <a href="/api/playlist-zip/{task_id}" download="{playlist_title}.zip" class="dl-all">⬇ Download All as ZIP</a>

  <div class="list-header">TRACKS</div>
  <div class="file-list">{rows_html}</div>
</body>
</html>"""
    return html

@app.route('/api/playlist-dl/<task_id>/<filename>')
def playlist_dl_single(task_id, filename):
    """Download a single MP3 from a completed playlist."""
    from urllib.parse import quote
    entry = completed_playlists.get(task_id)
    if not entry:
        return jsonify({"error": "Playlist not found"}), 404
    playlist_dir, _ = entry
    safe_name = os.path.basename(filename)
    fpath = os.path.join(playlist_dir, safe_name)
    if not os.path.exists(fpath):
        return jsonify({"error": "File not found"}), 404
    resp = send_file(fpath, as_attachment=True, download_name=safe_name, mimetype='audio/mpeg')
    resp.headers['Content-Disposition'] = f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{quote(safe_name)}'
    return resp

@app.route('/api/playlist-zip/<task_id>')
def playlist_zip(task_id):
    """Build and serve the ZIP on demand (for 'Download All' button)."""
    from urllib.parse import quote
    entry = completed_playlists.get(task_id)
    if not entry:
        return jsonify({"error": "Playlist not found"}), 404
    playlist_dir, playlist_title = entry
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname in sorted(os.listdir(playlist_dir)):
            if fname.lower().endswith('.mp3'):
                zf.write(os.path.join(playlist_dir, fname), fname)
    zip_buffer.seek(0)
    safe_title = re.sub(r'[^\w\-. ]', '_', playlist_title) + '.zip'
    resp = send_file(zip_buffer, as_attachment=True, download_name=safe_title, mimetype='application/zip')
    resp.headers['Content-Disposition'] = f'attachment; filename="{safe_title}"; filename*=UTF-8\'\'{quote(safe_title)}'
    return resp

@app.route('/api/get-file/<filename>')
def get_file(filename):
    """Legacy endpoint - redirects to the new /api/dl/ endpoint."""
    safe_filename = os.path.basename(filename)
    path = os.path.join(DOWNLOAD_DIR, safe_filename)
    if os.path.exists(path):
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_?'
        download_name = re.sub(uuid_pattern, '', safe_filename)
        download_name = re.sub(r'__+', '_', download_name).strip('_')
        if not download_name or download_name.startswith('.'):
            download_name = 'download.bin'
        response = send_file(path, as_attachment=True, download_name=download_name,
                             mimetype='application/octet-stream')
        from urllib.parse import quote
        response.headers['Content-Disposition'] = f"attachment; filename=\"{download_name}\"; filename*=UTF-8''{quote(download_name)}"
        return response
    return jsonify({"error": "File not found"}), 404

@app.route('/api/dl/<server_name>/<clean_name>')
def download_clean(server_name, clean_name):
    """Legacy path-based download endpoint."""
    safe_filename = os.path.basename(server_name)
    path = os.path.join(DOWNLOAD_DIR, safe_filename)
    if os.path.exists(path):
        safe_clean = os.path.basename(clean_name)
        response = send_file(path, as_attachment=True, download_name=safe_clean,
                             mimetype='application/octet-stream')
        from urllib.parse import quote
        response.headers['Content-Disposition'] = f"attachment; filename=\"{safe_clean}\"; filename*=UTF-8''{quote(safe_clean)}"
        return response
    return jsonify({"error": "File not found"}), 404

@app.route('/api/download')
def download_file_clean():
    """
    Primary download endpoint. Strips UUID prefixes and op-prefixes server-side
    so the browser always receives a human-readable filename.
    Usage: /api/download?file=<server_filename>
    """
    from urllib.parse import quote
    server_name = request.args.get('file', '').strip()
    if not server_name:
        return jsonify({"error": "No file specified"}), 400

    safe_filename = os.path.basename(server_name)
    path = os.path.join(DOWNLOAD_DIR, safe_filename)

    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404

    # 1. Strip UUID prefix: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx[_-]?
    clean_name = re.sub(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[_\-]?',
        '', safe_filename, flags=re.IGNORECASE
    )
    # 2. Strip known operation prefixes (e.g. compressed_, upscaled_, ...)
    clean_name = re.sub(
        r'^(compressed_|upscaled_|vectorized_|gemini_upscaled_|ai_enhanced_)',
        '', clean_name
    )
    # 3. Second-pass UUID strip (double-prefixed files)
    clean_name = re.sub(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[_\-]?',
        '', clean_name, flags=re.IGNORECASE
    )
    # 4. Remove any leading underscores / dashes
    clean_name = clean_name.lstrip('_-').strip()

    if not clean_name or clean_name.startswith('.'):
        clean_name = safe_filename   # fallback to raw name

    response = send_file(path, as_attachment=True, download_name=clean_name,
                         mimetype='application/octet-stream')
    response.headers['Content-Disposition'] = (
        f"attachment; filename=\"{clean_name}\"; filename*=UTF-8''{quote(clean_name)}"
    )
    return response

@app.route('/api/compress', methods=['POST'])
def compress_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    f = request.files['file']
    target_kb = request.form.get('target_kb', type=int)
    if not target_kb:
        return jsonify({"error": "target_kb is required"}), 400
        
    target_bytes = target_kb * 1024
    ext = os.path.splitext(f.filename)[1].lower()
    
    orig_name = re.sub(r'[\\/*?:"<>|]', "", f.filename).strip()
    if not orig_name:
        orig_name = f"file{ext}"
    out_filename = f"compressed_{uuid.uuid4()}_{orig_name}"
    out_path = os.path.join(DOWNLOAD_DIR, out_filename)
    
    if ext in ['.jpg', '.jpeg', '.png', '.webp']:
        img = Image.open(f)
        if img.mode in ('RGBA', 'P') and ext in ['.jpg', '.jpeg']:
            img = img.convert('RGB')
            
        if ext == '.png':
            img.save(out_path, format='PNG', optimize=True)
            # If PNG optimization isn't enough to hit target, it's a limitation without losing alpha or quantizing
            # We'll stick to optimize=True for PNG.
        else:
            low, high = 1, 95
            best_quality = high
            
            while low <= high:
                mid = (low + high) // 2
                temp_io = io.BytesIO()
                img.save(temp_io, format='JPEG', quality=mid)
                size = temp_io.tell()
                
                if size <= target_bytes:
                    best_quality = mid
                    low = mid + 1
                    if size >= target_bytes * 0.95:
                        break
                else:
                    high = mid - 1
                    
            img.save(out_path, format='JPEG', quality=best_quality)
                
    elif ext == '.pdf':
        doc = fitz.open(stream=f.read(), filetype="pdf")
        dpi = 150
        while dpi > 30:
            out_doc = fitz.open()
            for page in doc:
                pix = page.get_pixmap(dpi=dpi)
                img_data = pix.tobytes("jpeg")
                
                pdfbytes = fitz.open("pdf", fitz.open("jpeg", img_data).convert_to_pdf())
                out_doc.insert_pdf(pdfbytes)
                
            temp_path = out_path + "_temp"
            out_doc.save(temp_path, garbage=4, deflate=True)
            out_doc.close()
            
            size = os.path.getsize(temp_path)
            if size <= target_bytes or dpi <= 36:
                os.rename(temp_path, out_path)
                break
            os.remove(temp_path)
            dpi -= 20
        doc.close()
    else:
        out_filename = f"compressed_{uuid.uuid4()}_{orig_name}.zip"
        out_path = os.path.join(DOWNLOAD_DIR, out_filename)
        with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr(f.filename, f.read())
            
    return jsonify({"filename": out_filename})

@app.route('/api/upscale', methods=['POST'])
def upscale_image():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    f = request.files['file']
    fmt = request.form.get('format', 'A4')
    orientation = request.form.get('orientation', 'portrait')
    ai_enhance = request.form.get('ai_enhance', 'true') == 'true'
    
    if fmt == 'A4' or fmt == 'Poster':
        dims = (2480, 3508) if orientation == 'portrait' else (3508, 2480)
    elif fmt == 'A5':
        dims = (1748, 2480) if orientation == 'portrait' else (2480, 1748)
    else: # Wallpaper
        dims = (2160, 3840) if orientation == 'portrait' else (3840, 2160)
        
    target_w, target_h = dims
        
    try:
        img = Image.open(f)
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        orig_w, orig_h = img.size
        
        # Calculate scale needed to cover the target dims
        scale_w = target_w / orig_w
        scale_h = target_h / orig_h
        scale = max(scale_w, scale_h) # Use max to ensure we cover
        
        # Filter settings
        denoise = False
        contrast = 1.1 if ai_enhance else 1.0
        brightness = 0
        sharpness_radius = 1.5 if ai_enhance else 0.0
        sharpness_percent = 120
        
        # If Gemini guidance is enabled, try querying it for adjustments
        denoise = True
                
        # If we need to scale up significantly and AI Enhance is enabled
        if ai_enhance and scale > 1.1:
            # Convert PIL to OpenCV (RGB to BGR)
            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            
            # Apply Denoise on low-resolution image (highly efficient!)
            if denoise:
                cv_img = cv2.fastNlMeansDenoisingColored(cv_img, None, 10, 10, 7, 21)
                
            sr = cv2.dnn_superres.DnnSuperResImpl_create()
            sr.readModel(MODEL_PATH)
            sr.setModel("fsrcnn", 4)
            
            # Upscale iteratively if we need more than 4x
            current_scale = 1.0
            while current_scale < scale:
                cv_img = sr.upsample(cv_img)
                current_scale *= 4.0
                
            # Apply contrast/brightness adjustments
            if contrast != 1.0 or brightness != 0:
                cv_img = cv2.convertScaleAbs(cv_img, alpha=contrast, beta=brightness)
            
            # Convert back to PIL (BGR to RGB)
            img = Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))
            
        elif ai_enhance:
            # Scale is <= 1.1 but AI Enhance is checked, apply enhancements on original
            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            if denoise:
                cv_img = cv2.fastNlMeansDenoisingColored(cv_img, None, 10, 10, 7, 21)
            if contrast != 1.0 or brightness != 0:
                cv_img = cv2.convertScaleAbs(cv_img, alpha=contrast, beta=brightness)
            img = Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))
            
        # Resize to exactly cover the target canvas (Lanczos for final precise down/up scale)
        new_w = max(target_w, int(orig_w * scale))
        new_h = max(target_h, int(orig_h * scale))
        img = img.resize((new_w, new_h), resample=Image.LANCZOS)
        
        # Center crop to target dims
        left = (new_w - target_w) / 2
        top = (new_h - target_h) / 2
        right = (new_w + target_w) / 2
        bottom = (new_h + target_h) / 2
        img = img.crop((left, top, right, bottom))
        
        # Apply smart sharpening if AI Enhance is active
        if ai_enhance and sharpness_radius > 0:
            img = img.filter(ImageFilter.UnsharpMask(radius=sharpness_radius, percent=sharpness_percent, threshold=2))
        
        orig_clean = re.sub(r'[\\/*?:"<>|]', "", f.filename).strip()
        if not orig_clean:
            orig_clean = "image.jpg"
        else:
            base = os.path.splitext(orig_clean)[0]
            orig_clean = f"{base}.jpg"
            
        out_filename = f"upscaled_{uuid.uuid4()}_{orig_clean}"
        out_path = os.path.join(DOWNLOAD_DIR, out_filename)
        img.save(out_path, format='JPEG', quality=95)
        
        return jsonify({"filename": out_filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    print("Shutting down Flask server...")
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return jsonify({"status": "Shutting down application..."})

if __name__ == '__main__':
    app.run(debug=True, threaded=True, port=5000)
