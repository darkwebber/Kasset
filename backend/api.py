import os
import json
import logging
from typing import List, Optional
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from .core.cartridge_loader import CartridgeLoader
from .core.agent import Agent
from .core.persistence import chat_store, user_memory, ChatStore
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
    chat_id: Optional[str] = None  # For persistence

class FSRequest(BaseModel):
    path: str = str(Path.home())

class MemoryRequest(BaseModel):
    content: str
    memory_type: str = "fact"

class MemoryUpdateRequest(BaseModel):
    content: str

# --- Endpoints ---
@app.post("/api/fs/list")
def list_filesystem(request: FSRequest):
    """List directory contents for the frontend file browser."""
    try:
        p = Path(request.path).expanduser().resolve()
        if not p.exists() or not p.is_dir():
            return {"error": "Invalid directory"}
            
        items = []
        # Add parent directory if not root
        if p != p.parent:
            items.append({"name": "..", "path": str(p.parent), "type": "dir"})
            
        # Try to list contents
        try:
            for entry in p.iterdir():
                if entry.name.startswith("."): # skip hidden
                    continue
                is_dir = entry.is_dir()
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "dir" if is_dir else "file",
                    "size": entry.stat().st_size if not is_dir else 0
                })
        except PermissionError:
            return {"error": "Permission denied"}
            
        # Sort directories first, then alphabetically
        items.sort(key=lambda x: (0 if x["name"] == ".." else (1 if x["type"] == "dir" else 2), x["name"].lower()))
        
        return {
            "current_path": str(p),
            "items": items
        }
    except Exception as e:
        return {"error": str(e)}, 400

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
        
        # Generate or reuse chat_id
        chat_id = request.chat_id or ChatStore.generate_id()

        async def event_generator():
            # Send chat_id to frontend so it can track this conversation
            yield f"data: {json.dumps({'type': 'chat_id', 'data': chat_id})}\n\n"
            
            for event_json in agent.chat_stream(request.messages, request.image_path):
                yield f"data: {event_json}\n\n"
            
            # Auto-save conversation after streaming completes
            try:
                chat_store.save(chat_id, request.messages, request.cartridge_ids)
            except Exception as e:
                logger.warning(f"Auto-save failed: {e}")

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return {"error": str(e)}, 500


# ═══════════════════════════════════════════
# CHAT PERSISTENCE ENDPOINTS
# ═══════════════════════════════════════════

@app.get("/api/chats")
def list_chats():
    """List all saved conversations."""
    return {"chats": chat_store.list_all()}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str):
    """Load a specific conversation."""
    chat = chat_store.load(chat_id)
    if not chat:
        return {"error": "Chat not found"}, 404
    return {"chat": chat}

@app.post("/api/chats/{chat_id}/save")
async def save_chat(chat_id: str, request: Request):
    """Explicitly save/update a conversation."""
    body = await request.json()
    meta = chat_store.save(
        chat_id,
        body.get("messages", []),
        body.get("cartridge_ids", []),
        title=body.get("title", ""),
    )
    return {"saved": meta}

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str):
    """Delete a saved conversation."""
    ok = chat_store.delete(chat_id)
    return {"deleted": ok}


# ═══════════════════════════════════════════
# USER MEMORY ENDPOINTS
# ═══════════════════════════════════════════

@app.get("/api/memory")
def get_memories():
    """Get all user memories."""
    return {"memories": user_memory.get_all(active_only=False)}

@app.post("/api/memory")
def add_memory(request: MemoryRequest):
    """Manually add a user memory."""
    mem = user_memory.add(request.content, memory_type=request.memory_type, source="manual")
    return {"memory": mem}

@app.put("/api/memory/{memory_id}")
def update_memory(memory_id: str, request: MemoryUpdateRequest):
    """Update a user memory."""
    mem = user_memory.update(memory_id, request.content)
    if not mem:
        return {"error": "Memory not found"}, 404
    return {"memory": mem}

@app.delete("/api/memory/{memory_id}")
def delete_memory(memory_id: str):
    """Delete a user memory."""
    ok = user_memory.remove(memory_id)
    return {"deleted": ok}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7861)
