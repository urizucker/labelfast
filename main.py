from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

import base64
import fitz  # PyMuPDF

app = FastAPI(title="Labelfast API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store uploaded template as base64 image (simple v1 storage)
TEMPLATE_DATA_URL = None


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>Labelfast</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background: #f4f6f8;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                }
                .card {
                    background: white;
                    padding: 40px;
                    border-radius: 12px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                    text-align: center;
                }
                a { display:block; margin-top:10px; color:#111; text-decoration:none; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🚀 Labelfast</h1>
                <p>Cloud-based variable label printing platform.</p>
                <a href="/designer">Open Designer</a>
                <a href="/print">Open Print Preview</a>
            </div>
        </body>
    </html>
    """


@app.get("/print", response_class=HTMLResponse)
def print_label(w: float = 2.5, h: float = 3.0, text: str = "Sample Label"):
    html = """
    <html>
      <head>
        <style>
          @page {{
            size: {w}in {h}in;
            margin: 0;
          }}
          body {{ margin:0; font-family:Arial; }}
          .label {{
            width: {w}in;
            height: {h}in;
            display:flex;
            align-items:center;
            justify-content:center;
            font-size:16pt;
          }}
        </style>
      </head>
      <body>
        <div class="label">{text}</div>
        <script>window.print();</script>
      </body>
    </html>
    """.format(w=w, h=h, text=text)

    return html


@app.get("/designer", response_class=HTMLResponse)
def designer(w: float = 2.5, h: float = 3.0):
    global TEMPLATE_DATA_URL
    bg = TEMPLATE_DATA_URL or ""

    return """
    <html>
      <head>
        <title>Labelfast Designer</title>
        <style>
          body {{ font-family: Arial; margin:0; background:#f4f6f8; }}
          .topbar {{
            background:white;
            padding:12px;
            border-bottom:1px solid #ddd;
            display:flex;
            gap:10px;
            align-items:center;
          }}
          .btn {{
            padding:8px 12px;
            border-radius:8px;
            border:1px solid #ddd;
            background:#111;
            color:white;
            cursor:pointer;
          }}
          .label {{
            width:{w}in;
            height:{h}in;
            background:white;
            position:relative;
            margin:20px;
            box-shadow:0 10px 30px rgba(0,0,0,0.12);
          }}
          .bg {{
            position:absolute;
            inset:0;
            background-size:cover;
            background-position:center;
          }}
          .qr {{
            position:absolute;
            width:1in;
            height:1in;
            border:2px dashed #111;
            cursor:move;
            display:flex;
            align-items:center;
            justify-content:center;
            background:rgba(255,255,255,0.6);
          }}
        </style>
      </head>
      <body>
        <div class="topbar">
          <form action="/upload-template" method="post" enctype="multipart/form-data">
            <input type="file" name="file" accept=".png,.jpg,.jpeg,.pdf" required>
            <button class="btn">Upload</button>
          </form>
          <button class="btn" onclick="window.print()">Print</button>
          <a href="/" class="btn">Home</a>
        </div>

        <div class="label" id="label">
          <div class="bg" id="bg"></div>
          <div class="qr" id="qr" style="left:0.2in; top:0.2in;">QR</div>
        </div>

        <script>
          const bgData = {bg_json};

          if(bgData) {{
              document.getElementById('bg').style.backgroundImage = "url(" + bgData + ")";
          }}

          const qr = document.getElementById("qr");
          let dragging = false;
          let offsetX = 0;
          let offsetY = 0;

          qr.addEventListener("mousedown", e => {{
              dragging = true;
              offsetX = e.offsetX;
              offsetY = e.offsetY;
          }});

          document.addEventListener("mousemove", e => {{
              if(!dragging) return;
              const rect = document.getElementById("label").getBoundingClientRect();
              const pxPerIn = rect.width / {w};
              const leftIn = (e.clientX - rect.left - offsetX) / pxPerIn;
              const topIn = (e.clientY - rect.top - offsetY) / pxPerIn;
              qr.style.left = leftIn + "in";
              qr.style.top = topIn + "in";
          }});

          document.addEventListener("mouseup", () => dragging=false);
        </script>
      </body>
    </html>
    """.format(w=w, h=h, bg_json=repr(bg))


@app.post("/upload-template")
async def upload_template(file: UploadFile = File(...)):
    global TEMPLATE_DATA_URL

    content = await file.read()
    filename = file.filename.lower()

    if filename.endswith(".pdf"):
        pdf = fitz.open(stream=content, filetype="pdf")
        page = pdf.load_page(0)
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        TEMPLATE_DATA_URL = f"data:image/png;base64,{b64}"

    elif filename.endswith((".png", ".jpg", ".jpeg")):
        b64 = base64.b64encode(content).decode("utf-8")
        mime = file.content_type or "image/png"
        TEMPLATE_DATA_URL = f"data:{mime};base64,{b64}"

    return RedirectResponse(url="/designer", status_code=303)
