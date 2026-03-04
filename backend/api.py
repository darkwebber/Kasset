import os
import json
import logging
from typing import List, Optional
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .core.cartridge_loader import CartridgeLoader
from .core.agent import Agent
from .model_server import ModelClient # Refactored MLX wrapper

logger = logging.getLogger(__name__)

app = FastAPI(title="Qwen Studio Cartridge API")

# Allow Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize subsystems
model_client = ModelClient()
cartridge_loader = CartridgeLoader()

# --- API Models ---
class ChatRequest(BaseModel):
    cartridge_ids: List[str]
    messages: List[dict]
    image_path: Optional[str] = None

# --- Endpoints ---
@app.get("/api/cartridges")
def get_cartridges():
    """Returns all available cartridges."""
    return {"cartridges": cartridge_loader.list_available()}

@app.post("/api/cartridges/load")
def load_cartridge_stack(request: dict):
    """Returns the merged config for a stack of cartridges."""
    cartridge_ids = request.get("cartridge_ids", ["general-assistant"])
    try:
        config = cartridge_loader.load_stack(cartridge_ids)
        return {"config": config.model_dump()}
    except Exception as e:
        return {"error": str(e)}, 400

@app.post("/api/chat")
async def chat_stream(request: ChatRequest):
    """SSE endpoint for streaming chat with tool execution."""
    try:
        config = cartridge_loader.load_stack(request.cartridge_ids)
        agent = Agent(model_client, config)

        async def event_generator():
            for event_json in agent.chat_stream(request.messages, request.image_path):
                yield f"data: {event_json}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return {"error": str(e)}, 500

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7861)
