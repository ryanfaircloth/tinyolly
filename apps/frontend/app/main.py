# Entrypoint that delegates to main_entry.py for OLLYSCALE_MODE support
from app.main_entry import get_app

app = get_app()
