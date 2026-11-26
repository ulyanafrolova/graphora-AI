from fastapi import FastAPI

app = FastAPI()


@app.get("/api/items")
def list_items():
    return []


@app.post("/api/items")
def add_item():
    return {}
