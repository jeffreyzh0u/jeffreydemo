from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, Set
from enum import Enum
import json
import asyncio
from datetime import datetime

app = FastAPI()

class UserType(Enum):
    DRIVER = "driver"
    PASSENGER = "passenger"

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {
            UserType.DRIVER.value: {},
            UserType.PASSENGER.value: {}
        }
    
    async def connect(self, websocket: WebSocket, user_type: str, user_id: str):
        await websocket.accept()
        self.active_connections[user_type][user_id] = websocket
    
    def disconnect(self, user_type: str, user_id: str):
        self.active_connections[user_type].pop(user_id, None)
    
    async def send_personal_message(self, message: str, user_type: str, user_id: str):
        if websocket := self.active_connections[user_type].get(user_id):
            await websocket.send_text(message)
    
    async def broadcast(self, message: str, user_type: str):
        for connection in self.active_connections[user_type].values():
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/{user_type}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_type: str, user_id: str):
    try:
        await manager.connect(websocket, user_type, user_id)
        
        # Send connection confirmation
        await manager.send_personal_message(
            json.dumps({
                "type": "connection_established",
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": user_id
            }),
            user_type,
            user_id
        )
        
        try:
            while True:
                # Wait for messages from the client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle different message types
                if message.get("type") == "location_update":
                    # Process location update
                    await handle_location_update(message, user_type, user_id)
                elif message.get("type") == "ride_status":
                    # Process ride status update
                    await handle_ride_status(message, user_type, user_id)
                
        except WebSocketDisconnect:
            manager.disconnect(user_type, user_id)
            await manager.broadcast(
                json.dumps({
                    "type": "user_disconnected",
                    "user_id": user_id,
                    "timestamp": datetime.utcnow().isoformat()
                }),
                user_type
            )
    except Exception as e:
        print(f"Error handling websocket connection: {str(e)}")
        manager.disconnect(user_type, user_id)

async def handle_location_update(message: dict, user_type: str, user_id: str):
    """Handle location updates from drivers/passengers"""
    # Add timestamp to message
    message["timestamp"] = datetime.utcnow().isoformat()
    
    # Broadcast location update to relevant parties
    if user_type == UserType.DRIVER.value:
        await manager.broadcast(json.dumps(message), UserType.PASSENGER.value)
    else:
        await manager.broadcast(json.dumps(message), UserType.DRIVER.value)

async def handle_ride_status(message: dict, user_type: str, user_id: str):
    """Handle ride status updates"""
    message["timestamp"] = datetime.utcnow().isoformat()
    
    # Send status update to specific driver/passenger pair
    target_type = UserType.PASSENGER.value if user_type == UserType.DRIVER.value else UserType.DRIVER.value
    if target_id := message.get("target_id"):
        await manager.send_personal_message(
            json.dumps(message),
            target_type,
            target_id
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
