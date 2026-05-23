from flask import Flask, Response, request
import requests
import zipfile
import json
import io
import re
import os
import struct

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
    Parse ASTC file header (16 bytes).
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
    Convert ASTC binary data to PNG binary data (completed in-memory, without writing files).
    """
    block_w, block_h, width, height = parse_astc_header(astc_data)
    compressed = astc_data[16:]  # Skip header

    # texture2ddecoder.decode_astc(data, w, h, block_w, block_h)
    # Returns BGRA bytes
    raw_bgra = texture2ddecoder.decode_astc(compressed, width, height, block_w, block_h)

    img = Image.frombytes('RGBA', (width, height), raw_bgra, 'raw', 'BGRA')

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


# ─────────────────────────────────────────────
#  Flask route: Instantly convert ASTC to PNG and return
# ─────────────────────────────────────────────

@app.route('/proxy/astc')
def proxy_astc():
    """
    Usage: /proxy/astc?url=https://res.snakesvc.com/assets/xxx.astc
    The browser can use this directly as a normal PNG image.
    """
    url = request.args.get('url', '')
    if not url or not url.startswith('https://res.snakesvc.com/'):
        return 'Invalid URL', 400

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        png_bytes = astc_bytes_to_png_bytes(resp.content)
        return Response(png_bytes, mimetype='image/png')
    except Exception as e:
        return f'ASTC Conversion Failed: {e}', 500


# ─────────────────────────────────────────────
#  Shared Helpers
# ─────────────────────────────────────────────

def fetch_res_json(url: str, filename: str) -> dict:
    """Download zip and parse JSON, returning the resource dict."""
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        with zf.open(filename) as jf:
            return json.loads(jf.read().decode('utf-8'))


def build_file_url(key: str, meta: dict) -> str:
    """Construct full CDN URL based on key and meta from res['files']."""
    md5  = meta['md5']
    parts = key.rsplit('.', 1)          # ['login/bg', 'png'] or ['login/bg', 'astc']
    image_name = f"{parts[0]}.{md5}.{parts[1]}"
    return f"{ASSETS_URL}/{image_name}"


def get_login_images(res: dict) -> list:
    """
    Extract login image list from res dict (supports .png and .astc).
    Returns [(url, size), ...] sorted by size descending.
    """
    items = []
    for key, meta in res['files'].items():
        if key.startswith('login') and (key.endswith('.png') or key.endswith('.astc')):
            items.append((build_file_url(key, meta), meta['size']))
    return sorted(items, key=lambda x: x[1], reverse=True)


def get_main_scene_images(res: dict) -> list:
    """
    Extract mainScene image list from res dict (supports .png and .astc).
    Returns [(url, size), ...] sorted by size descending.
    """
    items = []
    for key, meta in res['files'].items():
        if key.startswith('mainScene') and (key.endswith('.png') or key.endswith('.astc')):
            items.append((build_file_url(key, meta), meta['size']))
    return sorted(items, key=lambda x: x[1], reverse=True)


def img_tag(url: str, style: str = 'max-width: 100%;') -> str:
    """
    Generate <img> tag based on file extension:
    - .png  → Use original URL directly
    - .astc → Real-time conversion via /proxy/astc route
    """
    if url.endswith('.astc'):
        from urllib.parse import quote
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

    html = "<div style='display:flex;flex-wrap:wrap;'>"
    for path, _ in scenes:
        html += f"<div style='flex:1 1 100px;margin:5px;'>{img_tag(path)}</div>"
    html += "</div>"
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
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)