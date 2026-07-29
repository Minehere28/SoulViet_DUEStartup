from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from views.assistant_view import router as assistant_router
from views.place_view import router as place_router
from views.travel_view import router

app = FastAPI()

app.include_router(router)
app.include_router(place_router)
app.include_router(assistant_router)

PROJECT_ROOT = Path(__file__).resolve().parent


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(PROJECT_ROOT / "static" / "index.html")
