from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import chess
from typing import Dict, List
import uvicorn
import os

app = FastAPI()

# Servir frontend estático
app.mount("/static", StaticFiles(directory="static"), name="static")

# Games in-memory (escalable: reemplaza por Redis)
games: Dict[str, Dict] = {}
connections: Dict[str, List[WebSocket]] = {}

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("static/index.html") as f:
        return HTMLResponse(f.read())

@app.get("/create_game")
async def create_game():
    game_id = str(len(games))  # Simple ID, usa UUID después
    games[game_id] = {
        "board": chess.Board(),
        "players": [],  # ["white_player_id", "black_player_id"]
        "spectators": []
    }
    connections[game_id] = []
    return {"game_id": game_id, "url": f"/game/{game_id}"}

@app.websocket("/ws/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    await websocket.accept()
    if game_id not in connections:
        await websocket.close(code=4000)
        return
    connections[game_id].append(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            msg = eval(data)  # Simple, usa JSON después
            if msg["type"] == "join":
                color = msg["color"]  # "white" or "black"
                games[game_id]["players"].append(color)
                await broadcast(game_id, {"type": "player_joined", "color": color})
            elif msg["type"] == "move":
                board = games[game_id]["board"]
                move = chess.Move.from_uci(msg["uci"])
                if move in board.legal_moves:
                    board.push(move)
                    await broadcast(game_id, {"type": "move", "fen": board.fen(), "uci": msg["uci"]})
                    if board.is_game_over():
                        await broadcast(game_id, {"type": "game_over", "result": board.result()})
    except WebSocketDisconnect:
        connections[game_id].remove(websocket)
    except Exception as e:
        print(f"Error: {e}")

async def broadcast(game_id: str, message: dict):
    for conn in connections.get(game_id, []):
        await conn.send_text(str(message))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))