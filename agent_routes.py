from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Log
from schemas import DiagnosisRequest, DiagnosisResponse
from agent import agent
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from database import get_db
from models import Log
from schemas import DiagnosisRequest, DiagnosisResponse
from agent import agent
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

def generate_diagnosis_html(data: dict):
    """Generates a modern, attractive HTML view for the diagnosis."""
    diagnosis = data["diagnosis"]
    
    # Define confidence color
    conf_color = "#10b981" if diagnosis["confidence"].lower() == "high" else "#f59e0b"
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Log Diagnosis</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
        <style>
            body {{ background-color: #f3f4f6; }}
            .card {{ background: white; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }}
            .badge {{ padding: 2px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }}
        </style>
    </head>
    <body class="p-8">
        <div class="max-w-4xl mx-auto">
            <header class="flex justify-between items-center mb-8">
                <div>
                    <h1 class="text-3xl font-bold text-gray-800">Log Diagnostician Agent</h1>
                    <p class="text-gray-500">AI-Powered Root Cause Analysis</p>
                </div>
                <div class="text-right">
                    <span class="text-sm text-gray-400">Execution Time</span>
                    <p class="text-xl font-mono font-bold text-blue-600">{data["execution_time_ms"]}ms</p>
                </div>
            </header>

            <div class="card p-6 mb-6 border-l-4 border-red-500">
                <div class="flex justify-between items-start mb-4">
                    <h2 class="text-lg font-semibold text-gray-700">Captured Error</h2>
                    <span class="badge bg-red-100 text-red-600">Log ID: {data["log_id"]}</span>
                </div>
                <code class="block p-4 bg-gray-900 text-green-400 rounded-lg font-mono text-sm">
                    {data["error_message"]}
                </code>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div class="md:col-span-2 space-y-6">
                    <section class="card p-6">
                        <div class="flex items-center mb-4">
                            <div class="p-2 bg-purple-100 rounded-lg mr-3">
                                <svg class="w-6 h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path></svg>
                            </div>
                            <h3 class="text-xl font-bold text-gray-800">Root Cause</h3>
                        </div>
                        <p class="text-gray-600 leading-relaxed">{diagnosis["root_cause"]}</p>
                    </section>

                    <section class="card p-6">
                        <div class="flex items-center mb-4">
                            <div class="p-2 bg-green-100 rounded-lg mr-3">
                                <svg class="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
                            </div>
                            <h3 class="text-xl font-bold text-gray-800">Suggested Fix</h3>
                        </div>
                        <div class="bg-gray-50 p-4 rounded-lg border border-gray-200">
                            <p class="text-gray-700 italic">{diagnosis["suggested_fix"]}</p>
                        </div>
                    </section>
                </div>

                <div class="space-y-6">
                    <section class="card p-6">
                        <h3 class="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Confidence</h3>
                        <div class="flex items-center">
                            <div class="w-3 h-3 rounded-full mr-2" style="background-color: {conf_color}"></div>
                            <span class="text-lg font-bold" style="color: {conf_color}">{diagnosis["confidence"]}</span>
                        </div>
                    </section>

                    <section class="card p-6">
                        <h3 class="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Prevention</h3>
                        <p class="text-sm text-gray-600">{diagnosis["prevention"]}</p>
                    </section>
                    
                    <button onclick="window.location.reload()" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-xl transition duration-200 shadow-lg">
                        Re-Analyze Latest
                    </button>
                </div>
            </div>
            
            <footer class="mt-12 text-center text-gray-400 text-sm">
                Built with Log Diagnostician Agent & Groq AI
            </footer>
        </div>
    </body>
    </html>
    """

@router.get("/diagnose/latest")
async def diagnose_latest_error(request: Request, db: Session = Depends(get_db)):
    # ... previous logic ...
    latest_error = db.query(Log).filter(Log.log_level.ilike("error")).order_by(Log.id.desc()).first()
    if not latest_error:
        raise HTTPException(status_code=404, detail="No error logs found")
    
    diagnosis = await agent.diagnose_error(latest_error)
    
    # If the request comes from a browser, show the pretty UI
    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(content=generate_diagnosis_html(diagnosis))
    
    return diagnosis

@router.post("/diagnose", response_model=DiagnosisResponse)
async def diagnose_specific_log(request: Request, diag_request: DiagnosisRequest, db: Session = Depends(get_db)):
    log_entry = db.query(Log).filter(Log.id == diag_request.log_id).first()
    if not log_entry:
        raise HTTPException(status_code=404, detail="Log not found")
    
    diagnosis = await agent.diagnose_error(log_entry)
    
    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(content=generate_diagnosis_html(diagnosis))
        
    return diagnosis
