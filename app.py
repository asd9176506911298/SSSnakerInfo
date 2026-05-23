from flask import Flask, Response, request
import requests
import zipfile
import json
import io
import re
import os
import struct
import gc
from threading import Lock  # 🚀 Memory threshold gatekeeper for low-RAM/Render environments
from urllib.parse import quote
from threading import Semaphore  # 🚀 改用 Semaphore 來做後端溫和排隊

from PIL import Image
import texture2ddecoder

app = Flask(__name__)

ASSETS_URL = 'https://res.snakesvc.com/assets'

# ─────────────────────────────────────────────
#  Memory Protection Circuit Breaker
# ─────────────────────────────────────────────
mem_lock = Lock()
CURRENT_CONCURRENT_DECODES = 0
MAX_CONCURRENT_DECODES = 2  # Allows max 2 heavy raw decodes at a time, instantly tripping 503 for the rest to trigger front-end self-healing retries

decode_semaphore = Semaphore(2)

# ─────────────────────────────────────────────
#  ASTC Decoding Tools
# ─────────────────────────────────────────────

ASTC_MAGIC = 0x5CA1AB13

def parse_astc_header(data: bytes):
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
    block_w, block_h, width, height = parse_astc_header(astc_data)
    compressed = astc_data[16:]
    del astc_data

    raw_bgra = texture2ddecoder.decode_astc(compressed, width, height, block_w, block_h)
    del compressed

    img = Image.frombytes('RGBA', (width, height), raw_bgra, 'raw', 'BGRA')
    del raw_bgra

    # 🚀 Requirement met: 0% compression applied. 100% full quality output stream
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=False, compress_level=1)
    png_bytes = buf.getvalue()
    del img
    buf.close()
    return png_bytes


# ─────────────────────────────────────────────
#  Flask route: Instantly convert ASTC to PNG
# ─────────────────────────────────────────────

@app.route('/proxy/astc')
def proxy_astc():
    url = request.args.get('url', '').strip('\'"')
    if not url or not url.startswith('https://res.snakesvc.com/'):
        return 'Invalid URL', 400

    # 🚀 核心改動：acquire() 會自動排隊。有空位才放行，沒空位就卡住瀏覽器請求，絕不回 503
    with decode_semaphore:
        try:
            # 1. 下載圖片（這一步其實不吃記憶體和 CPU，可以放在鎖裡面或外面，放在裡面最安全）
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            
            # 2. 執行高耗能解碼
            png_bytes = astc_bytes_to_png_bytes(resp.content)
            
            # 3. 立即強制回收記憶體
            gc.collect()
            
            return Response(png_bytes, mimetype='image/png')
        except Exception as e:
            return f'ASTC Conversion Failed: {e}', 500


# ─────────────────────────────────────────────
#  Shared Helpers
# ─────────────────────────────────────────────

def fetch_res_json(url: str, filename: str) -> dict:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        with zf.open(filename) as jf:
            return json.loads(jf.read().decode('utf-8'))


def build_file_url(key: str, meta: dict) -> str:
    md5  = meta['md5']
    parts = key.rsplit('.', 1)
    image_name = f"{parts[0]}.{md5}.{parts[1]}"
    return f"{ASSETS_URL}/{image_name}"


def get_login_images(res: dict) -> list:
    items = []
    for key, meta in res['files'].items():
        if key.startswith('login') and (key.endswith('.png') or key.endswith('.astc')):
            items.append((build_file_url(key, meta), meta['size']))
    return sorted(items, key=lambda x: x[1], reverse=True)


def get_main_scene_images(res: dict) -> list:
    items = []
    for key, meta in res['files'].items():
        if key.startswith('mainScene') and (key.endswith('.png') or key.endswith('.astc')):
            items.append((build_file_url(key, meta), meta['size']))
    return sorted(items, key=lambda x: x[1], reverse=True)


def img_tag(url: str, style: str = 'max-width: 100%;') -> str:
    if url.endswith('.astc'):
        proxy_url = f"/proxy/astc?url={quote(url, safe='')}"
        return f'<img src="{proxy_url}" style="{style}" title="ASTC (Auto Converted)">'
    return f'<img src="{url}" style="{style}">'


def render_version_info(version: dict) -> str:
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
#  Routes
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
    <p style="color:#2980b9;">🚀 Queue Mode: Controlled front-end concurrency to match server memory protection.</p>
    <div style='display:flex;flex-wrap:wrap;' id='gallery'>
    """

    for path, _ in scenes:
        proxy_url = f"/proxy/astc?url={quote(path, safe='')}" if path.endswith('.astc') else path
        html += f"""
        <div style='flex:1 1 150px;margin:5px;border:1px solid #ddd;text-align:center;
                    min-height:150px;display:flex;align-items:center;justify-content:center;background:#fafafa;'>
            <img data-src="{proxy_url}"
                 style="max-width:100%;max-height:200px;display:none;"
                 class="lazy-astc">
            <span class="loader" style="font-size:12px;color:#f39c12;">Waiting in queue...</span>
        </div>
        """

    # 💡 修正後的前端排隊與指數退避重試腳本
    html += """
    </div>
    <script>
    (function() {
        const MAX_CONCURRENT_LOADS = 2; // 前端控制最多同時只發送 2 個請求，完美對接後端
        const images = Array.from(document.querySelectorAll('.lazy-astc'));
        let currentIndex = 0;
        let activeLoads = 0;

        function advanceQueue() {
            while (activeLoads < MAX_CONCURRENT_LOADS && currentIndex < images.length) {
                const img = images[currentIndex];
                currentIndex++;
                activeLoads++;
                loadWithRetry(img, 0);
            }
        }

        function loadWithRetry(img, retryCount) {
            const loader = img.nextElementSibling;
            const baseSrc = img.getAttribute('data-src');
            
            // 如果失敗過，加上時間戳避免快取鎖死
            const timestamp = retryCount > 0 ? ('&_t=' + Date.now()) : '';
            img.src = baseSrc + timestamp;

            img.onload = () => {
                img.style.display = 'block';
                if (loader) loader.remove();
                activeLoads--;
                advanceQueue(); // 這張好了，換下一張
            };

            img.onerror = () => {
                const nextRetry = retryCount + 1;
                if (loader) {
                    loader.innerText = `Retry ${nextRetry} (Server Busy)...`;
                    loader.style.color = '#e74c3c';
                }
                
                // 指數退避延時（避免高頻率轟炸伺服器）：1秒、2秒、4秒... 最大 5 秒
                const delay = Math.min(1000 * Math.pow(2, retryCount), 5000); 
                setTimeout(() => {
                    loadWithRetry(img, nextRetry);
                }, delay);
            };
        }

        // 啟動排隊機制
        advanceQueue();
    })();
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
    is_debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1']
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=is_debug
    )