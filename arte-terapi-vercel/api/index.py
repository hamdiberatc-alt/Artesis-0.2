"""Single Vercel entry point. No HTTP server process is started on import."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['ARTE_CLOUD'] = '1'
from app import Handler

class handler(Handler):
    pass
