import os
import logging
import json
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Callable, Any
from dotenv import load_dotenv
from starlette.websockets import WebSocketDisconnect

from deepgram import DeepgramClient, LiveTranscriptionEvents
from modules.speech.meeting.meeting_minutes import process_audio

load_dotenv()

app = FastAPI()


templates = Jinja2Templates(directory="templates")
 
@app.get("/", response_class=HTMLResponse)
def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/meeting")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    deepgram_socket = None
    try:
        deepgram_socket = await process_audio(websocket)

        while True:
            try:
                data = await websocket.receive_bytes()
            except WebSocketDisconnect:
                break

            # MUST await async send
            await deepgram_socket.send(data)
    except Exception as e:
        raise Exception(f'Could not process audio: {e}')
    finally:
        try:
            if deepgram_socket:
                # finalize/finish gracefully
                if hasattr(deepgram_socket, "finalize"):
                    try:
                        await deepgram_socket.finalize()  # flush pending
                    except TypeError:
                        # finalize might be sync in some versions
                        deepgram_socket.finalize()
                if hasattr(deepgram_socket, "finish"):
                    try:
                        await deepgram_socket.finish()
                    except TypeError:
                        deepgram_socket.finish()
        finally:
            await websocket.close()