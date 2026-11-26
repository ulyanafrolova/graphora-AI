from fastapi import FastAPI

app = FastAPI()


@app.get("/users/me")
def me():
    return {}


@app.get("/users/{user_id}")
def user(user_id: int):
    return {}


@app.get("/users/{user_id}/orders")
def orders(user_id: int):
    return []
