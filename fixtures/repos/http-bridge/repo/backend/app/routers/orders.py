from fastapi import APIRouter

router = APIRouter(prefix="/orders")


@router.get("/{order_id}")
def get_order(order_id: int):
    return {}
