from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Labelfast API")

# Allow frontend connections later
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
                h1 {
                    margin-bottom: 10px;
                }
                p {
                    color: #666;
                }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🚀 Labelfast</h1>
                <p>Cloud-based variable label printing platform.</p>
                <p>Status: Backend is live.</p>
            </div>
        </body>
    </html>
    """
