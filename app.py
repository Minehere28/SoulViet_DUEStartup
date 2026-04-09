from fastapi import FastAPI
from views.travel_view import router

app = FastAPI()

app.include_router(router)