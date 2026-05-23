from flask import Flask, Response, request
import requests
import zipfile
import json
import io
import re
import os
import struct
import gc
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor  # 🚀 導入執行緒池
from urllib.parse import quote

from PIL import Image
import texture2ddecoder

app = Flask(__name__)

# 建立一個全局的執行緒池，專門用來處理背景圖片高並發下載與解碼
executor_pool = ThreadPoolExecutor(max_workers=4)

ASSETS_URL = 'https://res.snakesvc.com/assets'

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

    # 🚀 已經完全移除 MAX_SIZE 限制，這裡會輸出 100% 原始解析度的 PNG！

    buf = io.BytesIO()
    # 這裡可以把 compress_level 改為 3 或 4（原本是 1）
    # 因為不縮放了，原圖檔案會變大，稍微提升壓縮率可以幫你省下很多網路傳輸時間
    img.save(buf, format='PNG', optimize=False, compress_level=3)
    png_bytes = buf.getvalue()
    del img
    buf.close()
    return png_bytes

# ─────────────────────────────────────────────
#  Cache（加大快取到 128，避免大批圖時互相擠掉）
# ─────────────────────────────────────────────

@lru_cache(maxsize=128)
def fetch_and_decode_cached(url: str) -> bytes:
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    png_bytes = astc_bytes_to_png_bytes(resp.content)
    gc.collect()
    return png_bytes


def pre_decode_worker(url: str):
    """背景執行緒任務：靜默下載解碼並直接塞入 lru_cache"""
    try:
        fetch_and_decode_cached(url)
    except Exception as e:
        print(f"[背景解碼失敗] {url}: {e}")


# ─────────────────────────────────────────────
#  Flask Route: ASTC → PNG Proxy
# ─────────────────────────────────────────────

@app.route('/proxy/astc')
def proxy_astc():
    url = request.args.get('url', '').strip('\'"')

    if not url or 'res.snakesvc.com' not in url:
        return 'Invalid URL: Target domain not permitted', 400

    try:
        png_bytes = fetch_and_decode_cached(url)
        return Response(
            png_bytes,
            mimetype='image/png',
            headers={'Cache-Control': 'public, max-age=3600'}
        )
    except Exception as e:
        print(f"[proxy_astc] Error: {e}")
        return f'ASTC Conversion Failed: {e}', 500


# ─────────────────────────────────────────────
#  Shared Asset Helpers
# ─────────────────────────────────────────────

def fetch_res_json(url: str, filename: str) -> dict:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        with zf.open(filename) as jf:
            return json.loads(jf.read().decode('utf-8'))


def build_file_url(key: str, meta: dict) -> str:
    md5 = meta['md5']
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
#  Application Endpoints
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

    # 🚀 【核心優化點 1】：後端一拿到清單，立刻丟給背景執行緒池同時開跑下載與解碼
    astc_urls = [path for path, _ in scenes if path.endswith('.astc')]
    for target_url in astc_urls:
        executor_pool.submit(pre_decode_worker, target_url)

    html = """
    <h1 style="font-size:24px;">Main Scene Pictures</h1>
    <p style="color:#2ecc71;">✓ 已啟動背景群體高並發解碼管道...</p>
    <div style='display:flex;flex-wrap:wrap;' id='gallery'>
    """

    for path, _ in scenes:
        proxy_url = f"/proxy/astc?url={quote(path, safe='')}" if path.endswith('.astc') else path
        html += f"""
        <div style='flex:1 1 200px;margin:5px;border:1px solid #ccc;text-align:center;
                    min-height:150px;display:flex;align-items:center;justify-content:center;background:#f9f9f9;'>
            <img data-src="{proxy_url}"
                 style="max-width:100%;max-height:200px;display:none;"
                 class="lazy-astc">
            <span class="loader" style="font-size:12px;color:#999;">Waiting...</span>
        </div>
        """

    # 🚀 【核心優化點 2】：前端 MAX_CONCURRENT 放寬到 8，配合後端快速消化圖片
    html += """
    </div>
    <script>
    (function() {
        const MAX_CONCURRENT = 4;   // 解除 2 張限制，直接放大到 8 通道並行要圖！
        const MAX_RETRY      = 3;   
        const RETRY_DELAY_MS = 1500;

        const items = Array.from(document.querySelectorAll('.lazy-astc')).map(img => ({
            img,
            loader: img.nextElementSibling,
            retries: 0
        }));

        let active = 0;

        function loadNext() {
            if (items.length === 0) return;
            while (active < MAX_CONCURRENT && items.length > 0) {
                const item = items.shift();
                const { img, loader } = item;

                active++;
                if (loader) loader.innerText = 'Processing...';

                img.src = img.getAttribute('data-src');

                img.onload = () => {
                    img.style.display = 'block';
                    if (loader) loader.remove();
                    active--;
                    loadNext();
                };

                img.onerror = () => {
                    active--;
                    if (item.retries < MAX_RETRY) {
                        item.retries++;
                        if (loader) loader.innerText = `Retry ${item.retries}/${MAX_RETRY}...`;
                        const base = img.getAttribute('data-src').split('&_t=')[0];
                        img.setAttribute('data-src', base + '&_t=' + Date.now());
                        setTimeout(() => {
                            items.unshift(item);  
                            loadNext();
                        }, RETRY_DELAY_MS);
                    } else {
                        if (loader) {
                            loader.innerText = 'Failed ✗';
                            loader.style.color = '#c00';
                        }
                        loadNext();
                    }
                };
            }
        }

        // 一口氣把 8 個並發通道填滿發射出去
        loadNext();
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