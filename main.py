from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import base64
import fitz
import pandas as pd
import io
import qrcode

app = FastAPI(title="Labelfast API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATE_DATA_URL = None
METRC_CODES = []

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <body style="font-family:Arial;background:#f4f6f8;text-align:center;padding:100px;">
        <h1>🚀 Labelfast</h1>
        <a href="/designer">Open Designer</a>
    </body>
    </html>
    """

@app.get("/designer", response_class=HTMLResponse)
def designer(w: float = 2.5, h: float = 3.0, qr_size: float = 1.0):
    global TEMPLATE_DATA_URL

    return """
    <html>
    <head>
    <style>
        body {{ font-family:Arial;background:#f4f6f8;margin:0; }}
        .topbar {{ background:white;padding:10px;display:flex;gap:10px;flex-wrap:wrap; }}
        .label {{
            width:{w}in;
            height:{h}in;
            position:relative;
            background:white;
            margin:20px;
            box-shadow:0 10px 30px rgba(0,0,0,0.15);
        }}
        .bg {{
            position:absolute;inset:0;background-size:cover;background-position:center;
        }}
        .qr {{
            position:absolute;
            width:{qr_size}in;
            height:{qr_size}in;
            cursor:move;
        }}
        .idtext {{
            position:absolute;
            font-size:8pt;
            text-align:center;
            width:{qr_size}in;
        }}
        @media print {{
            body {{ margin:0;background:white; }}
            .topbar {{ display:none; }}
        }}
    </style>
    </head>
    <body>

    <div class="topbar">
        <form action="/upload-template" method="post" enctype="multipart/form-data">
            Template:
            <input type="file" name="file" accept=".png,.jpg,.jpeg,.pdf">
            <button>Upload</button>
        </form>

        <form action="/upload-metrc" method="post" enctype="multipart/form-data">
            METRC File:
            <input type="file" name="file" accept=".csv,.xlsx">
            <button>Upload</button>
        </form>

        <form method="get">
            W:<input type="number" step="0.1" name="w" value="{w}">
            H:<input type="number" step="0.1" name="h" value="{h}">
            QR Size:<input type="number" step="0.1" name="qr_size" value="{qr_size}">
            <button>Update</button>
        </form>

        <button onclick="window.location='/print-all?w={w}&h={h}&qr_size={qr_size}'">
            Print All
        </button>
    </div>

    <div class="label" id="label">
        <div class="bg" id="bg"></div>
        <div class="qr" id="qr" style="left:0.2in;top:0.2in;border:2px dashed black;"></div>
    </div>

    <script>
        const bgData = {bg};
        if(bgData) {{
            document.getElementById("bg").style.backgroundImage="url("+bgData+")";
        }}

        const qr = document.getElementById("qr");
        let dragging=false,offsetX=0,offsetY=0;

        qr.onmousedown = e => {{
            dragging=true;
            offsetX=e.offsetX;
            offsetY=e.offsetY;
        }};

        document.onmousemove = e => {{
            if(!dragging) return;
            const rect=document.getElementById("label").getBoundingClientRect();
            const pxPerIn=rect.width/{w};
            const left=(e.clientX-rect.left-offsetX)/pxPerIn;
            const top=(e.clientY-rect.top-offsetY)/pxPerIn;
            qr.style.left=left+"in";
            qr.style.top=top+"in";
        }};

        document.onmouseup=()=>dragging=false;
    </script>

    </body>
    </html>
    """.format(w=w,h=h,qr_size=qr_size,bg=repr(TEMPLATE_DATA_URL))

@app.post("/upload-template")
async def upload_template(file: UploadFile = File(...)):
    global TEMPLATE_DATA_URL
    content = await file.read()
    if file.filename.lower().endswith(".pdf"):
        pdf = fitz.open(stream=content, filetype="pdf")
        page = pdf.load_page(0)
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        TEMPLATE_DATA_URL = "data:image/png;base64," + base64.b64encode(img_bytes).decode()
    else:
        TEMPLATE_DATA_URL = "data:image/png;base64," + base64.b64encode(content).decode()
    return RedirectResponse("/designer",303)

@app.post("/upload-metrc")
async def upload_metrc(file: UploadFile = File(...)):
    global METRC_CODES
    content = await file.read()
    if file.filename.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    else:
        df = pd.read_excel(io.BytesIO(content))
    METRC_CODES = df["Unit Code"].dropna().tolist()
    return RedirectResponse("/designer",303)

@app.get("/print-all", response_class=HTMLResponse)
def print_all(w: float = 2.5, h: float = 3.0, qr_size: float = 1.0):
    global METRC_CODES, TEMPLATE_DATA_URL

    labels_html=""

    for code in METRC_CODES:
        qr_img = qrcode.make(code)
        buffer=io.BytesIO()
        qr_img.save(buffer, format="PNG")
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()

        labels_html+=f"""
        <div class="label">
            <div class="bg" style="background-image:url('{TEMPLATE_DATA_URL}')"></div>
            <img src="data:image/png;base64,{qr_base64}" 
                 style="position:absolute;width:{qr_size}in;height:{qr_size}in;left:0.2in;top:0.2in;">
            <div style="position:absolute;top:{0.2+qr_size}in;left:0.2in;width:{qr_size}in;font-size:8pt;text-align:center;">
                {code}
            </div>
        </div>
        """

    return f"""
    <html>
    <head>
    <style>
        @page {{ size:{w}in {h}in;margin:0; }}
        body {{ margin:0; }}
        .label {{
            width:{w}in;height:{h}in;position:relative;
        }}
        .bg {{ position:absolute;inset:0;background-size:cover; }}
    </style>
    </head>
    <body onload="window.print()">
    {labels_html}
    </body>
    </html>
    """
