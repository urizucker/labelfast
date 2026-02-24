from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Labelfast API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
                h1 { margin-bottom: 10px; }
                p { color: #666; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🚀 Labelfast</h1>
                <p>Cloud-based variable label printing platform.</p>
                <p>Status: Backend is live.</p>
                <p><a href="/print">Open Print Preview</a></p>
            </div>
        </body>
    </html>
    """

@app.get("/print", response_class=HTMLResponse)
def print_label(w: float = 2.5, h: float = 3.0, text: str = "Sample Label"):
    html = """
    <html>
      <head>
        <title>Labelfast Print</title>
        <style>
          @page {{
            size: {w}in {h}in;
            margin: 0;
          }}
          body {{
            margin: 0;
            padding: 0;
            background: #f4f6f8;
            font-family: Arial, sans-serif;
          }}
          .toolbar {{
            position: sticky;
            top: 0;
            background: white;
            border-bottom: 1px solid #ddd;
            padding: 12px;
            display: flex;
            gap: 10px;
            align-items: center;
          }}
          .btn {{
            padding: 10px 14px;
            border-radius: 10px;
            border: 1px solid #ddd;
            background: #111;
            color: white;
            cursor: pointer;
          }}
          .btn.secondary {{
            background: white;
            color: #111;
          }}
          .wrap {{
            padding: 18px;
          }}
          .label {{
            width: {w}in;
            height: {h}in;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.12);
            position: relative;
            overflow: hidden;
          }}
          .label-content {{
            padding: 14px;
            font-size: 14px;
          }}
          @media print {{
            body {{
              background: white;
            }}
            .toolbar, .wrap {{
              display: none !important;
            }}
            .print-area {{
              display: block !important;
              margin: 0;
              padding: 0;
            }}
            .label {{
              box-shadow: none;
              border-radius: 0;
            }}
          }}
        </style>
      </head>
      <body>
        <div class="toolbar">
          <button class="btn" onclick="window.print()">Print</button>
          <button class="btn secondary" onclick="window.location.href='/'">Back</button>
          <div style="color:#666;">Label size: {w}in × {h}in</div>
        </div>

        <div class="wrap">
          <div class="label">
            <div class="label-content">
              <h3 style="margin:0 0 6px 0;">{text}</h3>
              <div style="color:#666;">This is a print-accurate preview.</div>
              <div style="margin-top:10px; font-size:12px; color:#999;">Try: /print?w=2.5&h=3&text=Grams+Mimosa</div>
            </div>
          </div>
        </div>

        <div class="print-area" style="display:none;">
          <div class="label">
            <div class="label-content">
              <h3 style="margin:0 0 6px 0;">{text}</h3>
            </div>
          </div>
        </div>

      </body>
    </html>
    """.format(w=w, h=h, text=text)

    return html
