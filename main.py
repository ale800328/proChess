from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import chess
from typing import Dict, List
import json
import uvicorn
import os

app = FastAPI()

# Servir frontend
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/img", StaticFiles(directory="static/img"), name="img")  # ← Agregado para piezas directas en /img

# Almacén simple (escalable a Redis)
games: Dict[str, Dict] = {}
connections: Dict[str, List[WebSocket]] = {}

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("static/index.html") as f:
        return HTMLResponse(f.read())

@app.get("/create_game")
async def create_game():
    game_id = str(len(games))
    games[game_id] = {
        "board": chess.Board(),
        "players": [],  # ["white", "black"]
        "spectators": []
    }
    connections[game_id] = []
    return {"game_id": game_id}

@app.websocket("/ws/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    await websocket.accept()
    if game_id not in games:
        await websocket.close(code=4000)
        return
    connections[game_id].append(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            board = games[game_id]["board"]

            if msg["type"] == "join":
                color = msg["color"]
                if len(games[game_id]["players"]) < 2 and color not in games[game_id]["players"]:
                    games[game_id]["players"].append(color)
                    await broadcast(game_id, {"type": "player_joined", "color": color})
            elif msg["type"] == "move":
                uci_move = msg["uci"]
                move = chess.Move.from_uci(uci_move)
                if move in board.legal_moves:
                    board.push(move)
                    await broadcast(game_id, {
                        "type": "move",
                        "fen": board.fen(),
                        "uci": uci_move,
                        "san": board.san(move)  # Notación algebraica para lista de jugadas
                    })
                    if board.is_game_over():
                        await broadcast(game_id, {"type": "game_over", "result": board.result()})
    except WebSocketDisconnect:
        connections[game_id] = [c for c in connections[game_id] if c != websocket]
    except Exception as e:
        print(f"WS error: {e}")

async def broadcast(game_id: str, message: dict):
    for conn in connections.get(game_id, []):
        await conn.send_text(json.dumps(message))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
