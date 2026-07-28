import asyncio
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, hotel_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[hotel_id].add(websocket)

    def disconnect(self, hotel_id: int, websocket: WebSocket) -> None:
        self.connections[hotel_id].discard(websocket)
        if not self.connections[hotel_id]:
            self.connections.pop(hotel_id, None)

    async def broadcast(self, hotel_id: int, message: dict) -> None:
        stale: list[WebSocket] = []
        for websocket in list(self.connections.get(hotel_id, set())):
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(hotel_id, websocket)


manager = ConnectionManager()

