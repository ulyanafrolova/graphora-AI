from fastapi import FastAPI

from backend.app.routers import orders

app = FastAPI()
app.include_router(orders.router, prefix="/v1")
