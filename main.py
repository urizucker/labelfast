from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import base64
import fitz  # PyMuPDF
import pandas as pd
import io
import qrcode
import zipfile

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image


app = FastAPI(title="Labelfast API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Simple V1 in-memory storage (we'll replace with DB later) ---
TEMPLATE_DATA_URL = None       # background image as data URL (png)
METRC_CODES = []               # list of strings from "Unit Code" column

# saved layout in INCHES (what you see = what prints)
LAYOUT = {
    "w": 2.5,
    "h": 3.0,
    "qr_size": 0.5,
    "x": 0.2,   # left in inches
    "y": 0.2,   # top in inches
}

def display_text_from_unit_code(unit_code: str) -> str:
    """
    Your CSV uses full URLs like:
      HTTPS://1A4.COM/5LO1I9DSOCWXUZH9CCG0
    We display only the final segment as the 'number':
      5LO1I9DSOCWXUZH9CCG0
    """
    if not unit_code:
        return ""
    s = str(unit_code).strip()
    s = s.replace("\\", "/")
    # remove trailing slash
    if s.endswith("/"):
        s = s[:-1]
    # take last segment after /
    last = s.split("/")[-1]
    return last


def data_url_to_pil_image(data_url: str) -> Image.Image:
    """
    Convert data:image/png;base64,... -> PIL Image
    """
    if not data_url:
        raise ValueError("No template uploaded.")
    if "base64," not in data_url:
        raise ValueError("Invalid data URL.")
    b64 = data_url.split("base64,", 1)[1]
    raw = base64.b64decode(b64)
    return Image.open(io.BytesIO(raw)).convert("RGBA")


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
      <head>
        <style>
          body { font-family: Arial; background:#f4f6f8; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }
          .card { background:#fff; padding:28px; border-radius:14px; box-shadow:0 10px 30px rgba(0,0,0,0.12); width:520px; }
          a { display:inline-block; margin-top:10px; color:#111; text-decoration:none; }
          .muted { color:#666; }
        </style>
      </head>
      <body>
        <div class="card">
          <h2 style="margin:0 0 10px 0;">🚀 Labelfast</h2>
          <div class="muted">Cloud label designer + batch print.</div>
          <div style="margin-top:14px;">
            <a href="/designer">Open Designer</a>
          </div>
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
          input[type="number"] {{ width:86px; padding:8px; border-radius:10px; border:1px solid #ddd; }}
          .stage {{ padding:16px; }}
          .label {{
            width:{w}in; height:{h}in;
            background:white; position:relative; overflow:hidden;
            box-shadow:0 10px 30px rgba(0,0,0,0.12);
            border-radius:14px;
          }}
          .bg {{ position:absolute; inset:0; background-size:cover; background-position:center; }}
          .qr {{
            position:absolute;
            width:{qr_size}in; height:{qr_size}in;
            border:2px dashed #111; border-radius:12px;
            background: rgba(255,255,255,0.55);
            cursor: move; user-select:none;
            display:flex; align-items:center; justify-content:center;
            font-weight:700;
          }}
          .help {{ color:#666; font-size:12px; }}
          @media print {{
            body {{ background:white; margin:0; }}
            .topbar, .stage {{ display:none !important; }}
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
          </div>
          <div class="help" style="padding-top:10px;">
            Drag the QR box where it should print. Position is saved automatically.
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

          function savePos(leftIn, topIn) {{
            fetch('/api/layout', {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify({{ x:leftIn, y:topIn }})
            }});
          }}

          // Drag in inches
          const qr = document.getElementById('qrbox');
          const label = document.getElementById('label');
          let dragging = false;
          let startX=0, startY=0, startLeft=0, startTop=0;

          function parseIn(v) {{
            return parseFloat(String(v).replace('in','')) || 0;
          }}

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
          }});

          window.addEventListener('mouseup', ()=>{{
            if(!dragging) return;
            dragging = false;
            savePos(parseIn(qr.style.left), parseIn(qr.style.top));
          }});

          setBg();
        </script>
      </body>
    </html>
    """.format(
        w=w, h=h, qr_size=qr_size, x=x, y=y,
        count=count,
        bg_json=repr(bg)
    )


@app.post("/api/layout")
async def set_layout(payload: dict):
    # Update only provided keys
    for k in ["w", "h", "qr_size", "x", "y"]:
        if k in payload and payload[k] is not None:
            try:
                LAYOUT[k] = float(payload[k])
            except Exception:
                pass
    return {"ok": True, "layout": LAYOUT}


@app.post("/upload-template")
async def upload_template(file: UploadFile = File(...)):
    global TEMPLATE_DATA_URL
    content = await file.read()
    name = (file.filename or "").lower()

    # PDF -> png preview
    if name.endswith(".pdf"):
        pdf = fitz.open(stream=content, filetype="pdf")
        page = pdf.load_page(0)
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        TEMPLATE_DATA_URL = "data:image/png;base64," + base64.b64encode(img_bytes).decode()
    else:
        # png/jpg -> store as png data url (works fine)
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

    # Your file uses: "Unit Code"
    if "Unit Code" not in df.columns:
        # fallback: try case-insensitive match
        cols = {c.lower(): c for c in df.columns}
        if "unit code" in cols:
            col = cols["unit code"]
        else:
            METRC_CODES = []
            return RedirectResponse("/designer", status_code=303)
    else:
        col = "Unit Code"

    METRC_CODES = [str(x).strip() for x in df[col].dropna().tolist() if str(x).strip()]
    return RedirectResponse("/designer", status_code=303)


@app.get("/print-all", response_class=HTMLResponse)
def print_all():
    """
    Direct browser print (no download).
    Prints one label per METRC row.
    """
    w = LAYOUT["w"]
    h = LAYOUT["h"]
    qr_size = LAYOUT["qr_size"]
    x = LAYOUT["x"]
    y = LAYOUT["y"]

    bg = TEMPLATE_DATA_URL or ""
    labels_html = ""

    for i, code in enumerate(METRC_CODES, start=1):
        # QR encodes the full URL/code
        qr_img = qrcode.make(code)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()

        display = display_text_from_unit_code(code)

        labels_html += """
        <div class="label">
          <div class="bg" style="background-image:url('{bg}')"></div>
          <img src="data:image/png;base64,{qr}" style="position:absolute; left:{x}in; top:{y}in; width:{s}in; height:{s}in;" />
          <div class="txt" style="position:absolute; left:{x}in; top:{ty}in; width:{s}in;">
            {display}
            <div style="font-size:8pt; color:#666; margin-top:2px;">Metrc {n}</div>
          </div>
        </div>
        """.format(
            bg=bg,
            qr=qr_b64,
            x=x, y=y, s=qr_size,
            ty=(y + qr_size + 0.06),
            display=display,
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
          .txt {{ text-align:center; font-size:9pt; font-family:Arial; }}
        </style>
      </head>
      <body onload="window.print()">
        {labels}
      </body>
    </html>
    """.format(w=w, h=h, labels=labels_html)


@app.get("/export-zip")
def export_zip():
    """
    Creates a ZIP with one PDF per METRC label.
    This is for when you DO want separate PDFs (production + compliance archiving).
    """
    if not METRC_CODES:
        return RedirectResponse("/designer", status_code=303)
    if not TEMPLATE_DATA_URL:
        return RedirectResponse("/designer", status_code=303)

    w = LAYOUT["w"]
    h = LAYOUT["h"]
    qr_size = LAYOUT["qr_size"]
    x = LAYOUT["x"]
    y = LAYOUT["y"]

    # background as PIL image
    bg_img = data_url_to_pil_image(TEMPLATE_DATA_URL)

    # Create ZIP in memory
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for i, code in enumerate(METRC_CODES, start=1):
            display = display_text_from_unit_code(code)

            # QR image (PIL)
            qr_img = qrcode.make(code).convert("RGB")

            # Make PDF in memory
            pdf_buf = io.BytesIO()
            c = canvas.Canvas(pdf_buf, pagesize=(w * 72.0, h * 72.0))

            # Draw background to full page
            # reportlab uses points; images use pixels -> ImageReader handles it
            bg_reader = ImageReader(bg_img)
            c.drawImage(bg_reader, 0, 0, width=w * 72.0, height=h * 72.0, mask="auto")

            # Draw QR
            qr_reader = ImageReader(qr_img)
            c.drawImage(
                qr_reader,
                x * 72.0,
                (h - y - qr_size) * 72.0,  # convert from top-based inches to reportlab bottom origin
                width=qr_size * 72.0,
                height=qr_size * 72.0
            )

            # Draw text under QR (centered)
            text_y_top_based = y + qr_size + 0.06
            # convert top-based to bottom origin: y_from_bottom = (h - text_y - line_height)
            c.setFont("Helvetica", 8)
            c.drawCentredString(
                (x + qr_size / 2) * 72.0,
                (h - text_y_top_based - 0.12) * 72.0,
                display
            )
            c.setFont("Helvetica", 7)
            c.drawCentredString(
                (x + qr_size / 2) * 72.0,
                (h - text_y_top_based - 0.24) * 72.0,
                f"Metrc {i}"
            )

            c.showPage()
            c.save()

            pdf_bytes = pdf_buf.getvalue()
            safe_name = display.replace("/", "_").replace("\\", "_")
            z.writestr(f"{i:04d}_{safe_name}.pdf", pdf_bytes)

    zip_buf.seek(0)
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=labelfast_labels.zip"}
    )
