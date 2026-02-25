from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

import base64
import io
import zipfile

import fitz  # PyMuPDF
import pandas as pd
import qrcode
from PIL import Image

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


app = FastAPI(title="Labelfast API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# In-memory state (v1)
# -------------------------
TEMPLATE_DATA_URL = None  # background image stored as data:image/...;base64,...
METRC_CODES = []          # list of strings from CSV/XLSX "Unit Code"

# Saved layout in inches (WYSIWYG goal)
LAYOUT = {
    "w": 2.5,
    "h": 3.0,
    "qr_size": 0.5,
    "x": 0.2,   # left in inches (from left edge)
    "y": 0.2,   # top in inches  (from top edge)
}

# -------------------------
# Helpers
# -------------------------
def data_url_to_pil_image(data_url: str) -> Image.Image:
    if not data_url or "base64," not in data_url:
        raise ValueError("Template not available")
    b64 = data_url.split("base64,", 1)[1]
    raw = base64.b64decode(b64)
    return Image.open(io.BytesIO(raw)).convert("RGBA")


def ensure_template_exists() -> bool:
    return TEMPLATE_DATA_URL is not None and len(TEMPLATE_DATA_URL) > 30


# -------------------------
# Pages
# -------------------------
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
      <head>
        <style>
          body { font-family: Arial; background:#f4f6f8; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }
          .card { background:#fff; padding:28px; border-radius:14px; box-shadow:0 10px 30px rgba(0,0,0,0.12); width:560px; }
          .muted { color:#666; }
          a.btn { display:inline-block; margin-top:14px; padding:10px 14px; border-radius:10px; border:1px solid #ddd; background:#111; color:white; text-decoration:none; }
        </style>
      </head>
      <body>
        <div class="card">
          <h2 style="margin:0 0 10px 0;">🚀 Labelfast</h2>
          <div class="muted">Designer + batch print + separate-PDF export.</div>
          <a class="btn" href="/designer">Open Designer</a>
        </div>
      </body>
    </html>
    """


@app.get("/designer", response_class=HTMLResponse)
def designer():
    bg = TEMPLATE_DATA_URL or ""
    w = LAYOUT["w"]
    h = LAYOUT["h"]
    qr_size = LAYOUT["qr_size"]
    x = LAYOUT["x"]
    y = LAYOUT["y"]
    count = len(METRC_CODES)

    return """
    <html>
      <head>
        <title>Labelfast Designer</title>
        <style>
          body {{ font-family: Arial; background:#f4f6f8; margin:0; }}
          .topbar {{
            position: sticky; top:0; z-index:10;
            background:white; border-bottom:1px solid #ddd;
            padding:10px; display:flex; gap:10px; flex-wrap:wrap; align-items:center;
          }}
          .btn {{
            padding:9px 12px; border-radius:10px; border:1px solid #ddd;
            background:#111; color:#fff; cursor:pointer;
          }}
          .btn.secondary {{ background:#fff; color:#111; }}
          .field {{ display:flex; gap:6px; align-items:center; }}
          input[type="number"] {{ width:90px; padding:8px; border-radius:10px; border:1px solid #ddd; }}
          .help {{ color:#666; font-size:12px; }}
          .stage {{ padding:16px; }}
          .label {{
            width:{w}in; height:{h}in;
            background:white; position:relative; overflow:hidden;
            box-shadow:0 10px 30px rgba(0,0,0,0.12);
            border-radius:14px;
          }}
          .bg {{ position:absolute; inset:0; background-size:cover; background-position:center; background-repeat:no-repeat; }}
          .qr {{
            position:absolute;
            width:{qr_size}in; height:{qr_size}in;
            border:2px dashed #111; border-radius:12px;
            background: rgba(255,255,255,0.55);
            cursor: move; user-select:none;
            display:flex; align-items:center; justify-content:center;
            font-weight:700;
          }}
          .metrc {{
            position:absolute;
            left:{x}in;
            top:{ty2}in;
            width:{qr_size}in;
            text-align:center;
            font-size:9pt;
            color:#111;
            background: rgba(255,255,255,0.6);
            border-radius:8px;
            padding:2px 4px;
          }}
        </style>
      </head>
      <body>
        <div class="topbar">
          <form action="/upload-template" method="post" enctype="multipart/form-data" style="display:flex; gap:10px; align-items:center;">
            <span class="help">Template:</span>
            <input type="file" name="file" accept=".png,.jpg,.jpeg,.pdf" required>
            <button class="btn secondary" type="submit">Upload</button>
          </form>

          <form action="/upload-metrc" method="post" enctype="multipart/form-data" style="display:flex; gap:10px; align-items:center;">
            <span class="help">METRC:</span>
            <input type="file" name="file" accept=".csv,.xlsx" required>
            <button class="btn secondary" type="submit">Upload</button>
          </form>

          <div class="field">
            <span class="help">W(in)</span>
            <input id="w" type="number" step="0.01" value="{w}">
          </div>
          <div class="field">
            <span class="help">H(in)</span>
            <input id="h" type="number" step="0.01" value="{h}">
          </div>
          <div class="field">
            <span class="help">QR(in)</span>
            <input id="qr" type="number" step="0.01" value="{qr_size}">
          </div>

          <button class="btn secondary" onclick="applySize()">Apply</button>

          <button class="btn" onclick="window.location.href='/print-all'">Print All</button>
          <button class="btn" onclick="window.location.href='/export-zip'">Export Separate PDFs (ZIP)</button>

          <a class="btn secondary" href="/">Home</a>

          <span class="help">Loaded tags: <b>{count}</b></span>
        </div>

        <div class="stage">
          <div id="label" class="label">
            <div id="bg" class="bg"></div>

            <div id="qrbox" class="qr" style="left:{x}in; top:{y}in;">QR</div>
            <div id="metrcLabel" class="metrc">Metrc 1</div>
          </div>

          <div class="help" style="padding-top:10px;">
            Drag the QR box. Position saves when you release the mouse.
          </div>
        </div>

        <script>
          const bgData = {bg_json};

          function setBg() {{
            if(bgData) {{
              document.getElementById('bg').style.backgroundImage = "url(" + bgData + ")";
            }}
          }}

          function applySize() {{
            const w = parseFloat(document.getElementById('w').value || "{w}");
            const h = parseFloat(document.getElementById('h').value || "{h}");
            const qr = parseFloat(document.getElementById('qr').value || "{qr_size}");
            fetch('/api/layout', {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify({{ w:w, h:h, qr_size:qr }})
            }}).then(()=>window.location.reload());
          }}

          function parseIn(v) {{
            return parseFloat(String(v).replace('in','')) || 0;
          }}

          function syncMetrcLabel() {{
            const qr = document.getElementById('qrbox');
            const x = parseIn(qr.style.left);
            const y = parseIn(qr.style.top);
            const s = {qr_size};
            const m = document.getElementById('metrcLabel');
            m.style.left = x + "in";
            m.style.top  = (y + s + 0.12) + "in";
            m.style.width = s + "in";
          }}

          function savePos(leftIn, topIn) {{
            fetch('/api/layout', {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify({{ x:leftIn, y:topIn }})
            }});
          }}

          const qr = document.getElementById('qrbox');
          const label = document.getElementById('label');
          let dragging = false;
          let startX=0, startY=0, startLeft=0, startTop=0;

          qr.addEventListener('mousedown', (e)=>{{
            dragging = true;
            startX = e.clientX;
            startY = e.clientY;
            startLeft = parseIn(qr.style.left);
            startTop  = parseIn(qr.style.top);
            e.preventDefault();
          }});

          window.addEventListener('mousemove', (e)=>{{
            if(!dragging) return;
            const rect = label.getBoundingClientRect();
            const wIn = {w};
            const hIn = {h};
            const pxPerInX = rect.width / wIn;
            const pxPerInY = rect.height / hIn;
            const dxIn = (e.clientX - startX)/pxPerInX;
            const dyIn = (e.clientY - startY)/pxPerInY;
            const newLeft = Math.max(0, startLeft + dxIn);
            const newTop  = Math.max(0, startTop  + dyIn);
            qr.style.left = newLeft.toFixed(3) + "in";
            qr.style.top  = newTop.toFixed(3)  + "in";
            syncMetrcLabel();
          }});

          window.addEventListener('mouseup', ()=>{{
            if(!dragging) return;
            dragging = false;
            savePos(parseIn(qr.style.left), parseIn(qr.style.top));
          }});

          setBg();
          syncMetrcLabel();
        </script>
      </body>
    </html>
    """.format(
        w=w, h=h, qr_size=qr_size,
        x=x, y=y,
        ty2=(y + qr_size + 0.12),
        count=count,
        bg_json=repr(bg),
    )


# -------------------------
# API: save layout
# -------------------------
@app.post("/api/layout")
async def set_layout(payload: dict):
    for k in ["w", "h", "qr_size", "x", "y"]:
        if k in payload and payload[k] is not None:
            try:
                LAYOUT[k] = float(payload[k])
            except Exception:
                pass
    return {"ok": True, "layout": LAYOUT}


# -------------------------
# Uploads
# -------------------------
@app.post("/upload-template")
async def upload_template(file: UploadFile = File(...)):
    global TEMPLATE_DATA_URL
    content = await file.read()
    name = (file.filename or "").lower()

    if name.endswith(".pdf"):
        pdf = fitz.open(stream=content, filetype="pdf")
        page = pdf.load_page(0)
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        TEMPLATE_DATA_URL = "data:image/png;base64," + base64.b64encode(img_bytes).decode()
    else:
        mime = file.content_type or "image/png"
        TEMPLATE_DATA_URL = f"data:{mime};base64," + base64.b64encode(content).decode()

    return RedirectResponse("/designer", status_code=303)


@app.post("/upload-metrc")
async def upload_metrc(file: UploadFile = File(...)):
    global METRC_CODES
    content = await file.read()
    name = (file.filename or "").lower()

    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    else:
        df = pd.read_excel(io.BytesIO(content))

    # expects "Unit Code"
    col = None
    if "Unit Code" in df.columns:
        col = "Unit Code"
    else:
        cols = {c.lower(): c for c in df.columns}
        if "unit code" in cols:
            col = cols["unit code"]

    if not col:
        METRC_CODES = []
        return RedirectResponse("/designer", status_code=303)

    METRC_CODES = [str(x).strip() for x in df[col].dropna().tolist() if str(x).strip()]
    return RedirectResponse("/designer", status_code=303)


# -------------------------
# Print All (direct print)
# -------------------------
@app.get("/print-all", response_class=HTMLResponse)
def print_all():
    w = LAYOUT["w"]
    h = LAYOUT["h"]
    s = LAYOUT["qr_size"]
    x = LAYOUT["x"]
    y = LAYOUT["y"]
    bg = TEMPLATE_DATA_URL or ""

    if not METRC_CODES:
        return """
        <html><body style="font-family:Arial;padding:30px;">
          <h3>No METRC tags loaded.</h3>
          <a href="/designer">Back to Designer</a>
        </body></html>
        """

    labels_html = ""
    for i, code in enumerate(METRC_CODES, start=1):
        qr_img = qrcode.make(code)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()

        labels_html += """
        <div class="label">
          <div class="bg" style="background-image:url('{bg}')"></div>
          <img src="data:image/png;base64,{qr}" style="position:absolute; left:{x}in; top:{y}in; width:{s}in; height:{s}in;" />
          <div class="sub" style="position:absolute; left:{x}in; top:{ty}in; width:{s}in;">
            Metrc {n}
          </div>
        </div>
        """.format(
            bg=bg,
            qr=qr_b64,
            x=x, y=y, s=s,
            ty=(y + s + 0.12),
            n=i
        )

    return """
    <html>
      <head>
        <style>
          @page {{ size:{w}in {h}in; margin:0; }}
          body {{ margin:0; }}
          .label {{ width:{w}in; height:{h}in; position:relative; overflow:hidden; }}
          .bg {{ position:absolute; inset:0; background-size:cover; background-position:center; background-repeat:no-repeat; }}
          .sub {{ text-align:center; font-size:9pt; font-family:Arial; color:#111; background: rgba(255,255,255,0.0); }}
        </style>
      </head>
      <body onload="window.print()">
        {labels}
      </body>
    </html>
    """.format(w=w, h=h, labels=labels_html)


# -------------------------
# Export ZIP (separate PDFs)
# -------------------------
@app.get("/export-zip")
def export_zip():
    if not METRC_CODES:
        return RedirectResponse("/designer", status_code=303)
    if not ensure_template_exists():
        return RedirectResponse("/designer", status_code=303)

    w = LAYOUT["w"]
    h = LAYOUT["h"]
    s = LAYOUT["qr_size"]
    x = LAYOUT["x"]
    y = LAYOUT["y"]

    bg_img = data_url_to_pil_image(TEMPLATE_DATA_URL)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for i, code in enumerate(METRC_CODES, start=1):
            qr_img = qrcode.make(code).convert("RGB")

            pdf_buf = io.BytesIO()
            c = canvas.Canvas(pdf_buf, pagesize=(w * 72.0, h * 72.0))

            bg_reader = ImageReader(bg_img)
            c.drawImage(bg_reader, 0, 0, width=w * 72.0, height=h * 72.0, mask="auto")

            qr_x_pt = x * 72.0
            qr_y_pt = (h - y - s) * 72.0

            qr_reader = ImageReader(qr_img)
            c.drawImage(qr_reader, qr_x_pt, qr_y_pt, width=s * 72.0, height=s * 72.0)

            # Only "Metrc X"
            c.setFont("Helvetica", 7)
            sub_top = y + s + 0.12
            c.drawCentredString(
                (x + s / 2) * 72.0,
                (h - sub_top - 0.12) * 72.0,
                f"Metrc {i}"
            )

            c.showPage()
            c.save()

            z.writestr(f"{i:04d}_metrc_{i}.pdf", pdf_buf.getvalue())

    zip_buf.seek(0)
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=labelfast_labels.zip"}
    )
