from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  
from views.travel_view import router

app = FastAPI()

# Cấu hình CORS để giao diện có thể gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Cho phép tất cả các nguồn (để test)
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)