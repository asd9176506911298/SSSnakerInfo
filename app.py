from flask import Flask, Response, request
import requests
import zipfile
import json
import io
import re
import os
import struct
import gc  # Imported for manual garbage collection

from PIL import Image
import texture2ddecoder

app = Flask(__name__)

ASSETS_URL = 'https://res.snakesvc.com/assets'

# ─────────────────────────────────────────────
#  ASTC Decoding Tools
# ─────────────────────────────────────────────

ASTC_MAGIC = 0x5CA1AB13

def parse_astc_header(data: bytes):
    """
    Parses the 16-byte ASTC file header.
    Returns (block_w, block_h, width, height) or raises ValueError if format is invalid.
    """
    if len(data) < 16:
        raise ValueError("Data too short to be a valid ASTC file")

    magic, block_w, block_h, block_d, \
    xsize_lo, xsize_mi, xsize_hi, \
    ysize_lo, ysize_mi, ysize_hi, \
    zsize_lo, zsize_mi, zsize_hi = struct.unpack_from('<IBBBBBBBBBBBB', data, 0)

    if magic != ASTC_MAGIC:
        raise ValueError(f"Magic number mismatch: {hex(magic)}")

    width  = xsize_lo | (xsize_mi << 8) | (xsize_hi << 16)
    height = ysize_lo | (ysize_mi << 8) | (ysize_hi << 16)

    return block_w, block_h, width, height


def astc_bytes_to_png_bytes(astc_data: bytes) -> bytes:
    """
    Converts ASTC binary data to PNG binary data in-memory.
    Includes explicit memory cleanup to prevent Render OOM (Out Of Memory) crashes.
    """
    block_w, block_h, width, height = parse_astc_header(astc_data)
    compressed = astc_data[16:]  # Skip the 16-byte header

    # texture2ddecoder.decode_astc returns raw BGRA bytes
    raw_bgra = texture2ddecoder.decode_astc(compressed, width, height, block_w, block_h)
    img = Image.frombytes('RGBA', (width, height), raw_bgra, 'raw', 'BGRA')

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    png_bytes = buf.getvalue()

    # Explicitly delete massive byte arrays and close buffers to free RAM instantly
    del compressed
    del raw_bgra
    del img
    buf.close()
    
    # Force Python garbage collector to reclaim leaked memory fragments
    gc.collect() 

    return png_bytes


# ─────────────────────────────────────────────
#  Flask Route: On-the-fly ASTC to PNG Proxy
# ─────────────────────────────────────────────

@app.route('/proxy/astc')
def proxy_astc():
    """
    Usage: /proxy/astc?url=https://res.snakesvc.com/assets/xxx.astc
    Converts individual ASTC textures to standard browser-readable PNG formats.
    """
    url = request.args.get('url', '')
    
    # Strip accidental extra quotes or whitespace injected by browser proxying
    url = url.strip('\'"') 
    
    # Loosened restriction check to tolerate HTTP/HTTPS routing schemes on reverse-proxies
    if not url or 'res.snakesvc.com' not in url:
        return 'Invalid URL: Target domain not permitted', 400

    try:
        # Include standard User-Agent headers to avoid getting blocklisted by target asset CDN
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        png_bytes = astc_bytes_to_png_bytes(resp.content)
        return Response(png_bytes, mimetype='image/png')
    except Exception as e:
        # Logs errors explicitly into the Render Host Dashboard console
        print(f"Error converting ASTC texture: {e}")
        return f'ASTC Conversion Failed: {e}', 500


# ─────────────────────────────────────────────
#  Shared Asset Helpers
# ─────────────────────────────────────────────

def fetch_res_json(url: str, filename: str) -> dict:
    """Downloads remote version archive package and extracts configuration schema manifest metadata."""
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        with zf.open(filename) as jf:
            return json.loads(jf.read().decode('utf-8'))


def build_file_url(key: str, meta: dict) -> str:
    """Constructs authenticated target CDN asset location string maps."""
    md5  = meta['md5']
    parts = key.rsplit('.', 1)  # splits structure target array into filename and format keys
    image_name = f"{parts[0]}.{md5}.{parts[1]}"
    return f"{ASSETS_URL}/{image_name}"


def get_login_images(res: dict) -> list:
    """Extracts UI landing splash files sorted by file size weight limits."""
    items = []
    for key, meta in res['files'].items():
        if key.startswith('login') and (key.endswith('.png') or key.endswith('.astc')):
            items.append((build_file_url(key, meta), meta['size']))
    return sorted(items, key=lambda x: x[1], reverse=True)


def get_main_scene_images(res: dict) -> list:
    """Extracts standard operational rendering canvas graphics environments metadata."""
    items = []
    for key, meta in res['files'].items():
        if key.startswith('mainScene') and (key.endswith('.png') or key.endswith('.astc')):
            items.append((build_file_url(key, meta), meta['size']))
    return sorted(items, key=lambda x: x[1], reverse=True)


def img_tag(url: str, style: str = 'max-width: 100%;') -> str:
    """Generates standard image embedding nodes based on specific compression parameters."""
    if url.endswith('.astc'):
        from urllib.parse import quote
        proxy_url = f"/proxy/astc?url={quote(url, safe='')}"
        return f'<img src="{proxy_url}" style="{style}" title="ASTC (Auto Converted)">'
    return f'<img src="{url}" style="{style}">'


def render_version_info(version: dict) -> str:
    """Auxiliary layout helper mapping configuration labels."""
    return (
        f"branch: {version['branch']}<br>"
        f"short_id: {version['short_id']}<br>"
        f"datetime: {version['datetime']}<br>"
        f"msg: {version['msg']}<br>"
    )


COMMON_BUTTONS = '''
    <form action="/currentMobileVersion" method="post">
        <button type="submit" style="width:300px;height:50px;font-size:20px;margin:4px;">Get Current Version</button>
    </form>
    <form action="/" method="get">
        <button type="submit" style="width:500px;height:50px;font-size:20px;margin:4px;">Cdn Version (UnPublish)</button>
    </form>
    <form action="/query" method="post" style="margin-top:8px;">
        <input type="text" name="short_id" placeholder="Enter short_id" required style="font-size:16px;padding:4px;">
        <button type="submit" style="width:100px;height:30px;font-size:16px;">Query</button>
    </form>
'''


def render_version_page(title: str, res: dict, short_id: str | None = None) -> str:
    """Assembles base dashboard tracking components interfaces templates layout forms."""
    login_sorted = get_login_images(res)
    version = res['version']

    scene_hidden = f'<input type="hidden" name="short_id" value="{short_id}">' if short_id else ''

    html  = f'<h1 style="font-size:24px;">{title}</h1>'
    html += render_version_info(version)
    html += 'Login Image:<br>'
    html += img_tag(login_sorted[0][0], 'max-width:500px;') if login_sorted else '<p>Login image not found</p>'
    html += f'''
    <form action="/getmainScenePicture" method="post" style="margin-top:8px;">
        {scene_hidden}
        <button type="submit" style="width:300px;height:50px;font-size:20px;margin:4px;">Get Main Scene Pictures</button>
    </form>
    '''
    html += COMMON_BUTTONS
    return html


# ─────────────────────────────────────────────
#  Application Endpoints Routes
# ─────────────────────────────────────────────

@app.route('/')
def index():
    url = "https://res.snakesvc.com/assets/res.json"
    res = fetch_res_json(url, 'res.json')
    return render_version_page('Cdn Version (UnPublish Version)', res)


@app.route('/currentMobileVersion', methods=['POST'])
def currentMobileVersion():
    raw_data = bytes([
        0x46, 0x46, 0x46, 0x46, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x77, 0x18, 0x8B, 0xEC, 0x00, 0x05, 0x00, 0x00, 0x00, 0x17, 0x31, 0x2E,
        0x32, 0x01, 0x1A, 0x05, 0x31, 0x2E, 0x2E, 0x31, 0x2E, 0x33, 0x10, 0x11,
        0x0A, 0x06, 0x76, 0x31, 0x0A, 0x02, 0x10, 0x00, 0x12
    ])
    api_res = requests.post(
        url='https://game.snakesvc.com/api/front/v1/version/GetReview',
        data=raw_data,
        timeout=15
    )
    r = api_res.text[30:]
    r = r[-13::-1]
    filtered = re.findall(r'[a-z0-9]{8}', r)
    short_id = filtered[1]

    filename = f'res.{short_id}.json'
    url = f'https://res.snakesvc.com/res-version/{filename}'
    res = fetch_res_json(url, filename)

    return render_version_page('Current Mobile Version', res, short_id=short_id)


@app.route('/getmainScenePicture', methods=['POST'])
def getmainScenePicture():
    """
    Renders the scene picture array gallery.
    Uses sequential client-side asynchronous queue management via JS 
    to stop concurrent processing spikes on weak cloud hardware systems.
    """
    if 'short_id' in request.form:
        short_id = request.form.get('short_id')
        filename = f'res.{short_id}.json'
        url = f'https://res.snakesvc.com/res-version/{filename}'
    else:
        filename = 'res.json'
        url = "https://res.snakesvc.com/assets/res.json"

    res = fetch_res_json(url, filename)
    scenes = get_main_scene_images(res)

    html = """
    <h1 style="font-size:24px;">Main Scene Pictures</h1>
    <p style="color:#666;">Processing images inside sequential pipeline queues to prevent 513/503 Render crashes...</p>
    <div style='display:flex;flex-wrap:wrap;' id='gallery'>
    """
    
    for path, _ in scenes:
        from urllib.parse import quote
        proxy_url = f"/proxy/astc?url={quote(path, safe='')}" if path.endswith('.astc') else path
        
        # Hide the proxy location inside a data-src parameter to hold loading back
        html += f"""
        <div style='flex:1 1 200px; margin:5px; border:1px solid #ccc; text-align:center; min-height:150px; display:flex; align-items:center; justify-content:center; background:#f9f9f9;'>
            <img data-src="{proxy_url}" style="max-width:100%; max-height:200px; display:none;" class="lazy-astc">
            <span style="font-size:12px; color:#999;" class="loader">Queueing...</span>
        </div>
        """
        
    # JavaScript Payload: Implements a concurrency throttling pattern (max 2 parallel asset transformations)
    html += """
    </div>
    <script>
        const images = Array.from(document.querySelectorAll('.lazy-astc'));
        const MAX_CONCURRENT = 2; 
        let activeRequests = 0;

        function loadNext() {
            if (images.length === 0) return;
            if (activeRequests >= MAX_CONCURRENT) return;

            const img = images.shift();
            const loader = img.nextElementSibling;
            
            activeRequests++;
            if (loader) loader.innerText = "Processing...";
            
            // Re-assigning data-src to standard src starts targeted pipeline sequence execution
            img.src = img.getAttribute('data-src');
            
            img.onload = img.onerror = () => {
                img.style.display = 'block';
                if (loader) loader.remove();
                activeRequests--;
                
                // Triggers immediate loop iteration for next item pending inside collection
                loadNext(); 
            };

            // Attempt to keep concurrent lanes packed under hardware threshold limit guidelines
            loadNext();
        }

        // Initialize queue worker processes thread loops
        for (let i = 0; i < MAX_CONCURRENT; i++) {
            loadNext();
        }
    </script>
    """
    return html


@app.route('/query', methods=['POST'])
def query_short_id():
    short_id = request.form['short_id']
    filename = f'res.{short_id}.json'
    url = f'https://res.snakesvc.com/res-version/{filename}'

    resp = requests.get(url, timeout=15)
    if resp.status_code == 404:
        return '<h1 style="font-size:24px;">Error Short_id</h1>'

    res = fetch_res_json(url, filename)
    return render_version_page(f'Query Specify {short_id} Version', res, short_id=short_id)


if __name__ == '__main__':
    # Safely switches Flask configuration flags checking deployment container system environment parameters
    is_debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1']
    
    app.run(
        host='0.0.0.0', 
        port=int(os.environ.get('PORT', 5000)), 
        debug=is_debug
    )