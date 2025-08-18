import os
import logging
import json
import asyncio
import io 
import uuid
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Callable, Any
from dotenv import load_dotenv
from starlette.websockets import WebSocketDisconnect

from deepgram import DeepgramClient, LiveTranscriptionEvents
from modules.speech.meeting.meeting_minutes import process_audio
from modules.speech.live.live_gemini import gemini_live_stream
from modules.speech.audio_format import save_audio_buffer_as_wav
load_dotenv()

app = FastAPI()
logger = logging.getLogger("deepgram")
logger.setLevel(logging.INFO)

templates = Jinja2Templates(directory="templates")
 
@app.get("/", response_class=HTMLResponse)
def get(request: Request):
    return templates.TemplateResponse("test_voice_chat.html", {"request": request})

@app.websocket("/meeting")
async def websocket_meeting(websocket: WebSocket):
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

@app.websocket("/live")
async def websocket_live(websocket: WebSocket):
    await websocket.accept()
    
    # Generate a unique ID for this connection
    remote_user_id = f"user_{id(websocket)}"
    manager = None
    
    try:
        print(f"New WebSocket connection: {remote_user_id}")
        
        # Create and initialize the Gemini session manager
        from modules.speech.live.websocket_gemini import WebSocketGeminiManager
        manager = WebSocketGeminiManager(remote_user_id)
        
        # Start the Gemini session
        gemini_session = await manager.start_session(websocket)
        
        # Process incoming audio data
        while True:
            try:
                # Receive binary audio data from client
                data = await websocket.receive_bytes()
                
                # Process the audio data through the manager
                success = await manager.process_audio_bytes(data)
                if not success:
                    print(f"Failed to process audio for {remote_user_id}")
                    break
                    
            except WebSocketDisconnect:
                print(f"WebSocket disconnected for user: {remote_user_id}")
                break
    
    except Exception as e:
        print(f"Error in live WebSocket connection: {e}")
        
    finally:
        # Clean up resources
        if manager:
            await manager.stop_session()
        
        # Ensure WebSocket is closed
        if websocket.client_state.name == 'CONNECTED':
            await websocket.close()
            
        print(f"WebSocket connection closed: {remote_user_id}")






@app.websocket("/ws/voice-chat")
async def voice_chat_websocket(websocket: WebSocket):
    """WebSocket endpoint for voice chat with authentication and session management."""
    
    # Các biến mặc định
    # model_id = "gemini/gemini-2.0-flash"
    # model_id = "gemini-2.5-flash-preview-native-audio-dialog"
    model_id = "gemini-live-2.5-flash-preview"
    voice = "alloy"
    session_id = None
    parent_response_id = None
    project_id = None
    current_user = None
    user_language = "en"

    is_recording = False
    audio_buffer = io.BytesIO()
    
    try:
        # Chấp nhận kết nối WebSocket
        await websocket.accept()
        logger.info("WebSocket connection accepted")
        
        # Nhận dữ liệu xác thực từ client
        auth_data = await websocket.receive_json()
        
        # Gửi thông báo xác thực thành công
        await websocket.send_json({"type": "connection_ready", "message": "Authentication successful"})

        # Xử lý tin nhắn từ client
        while True:
            message = await websocket.receive()
            
            # binary frames
            if "bytes" in message and message["bytes"] is not None:
                if is_recording:
                    audio_buffer.write(message["bytes"])
                continue
            
            # Xử lý tin nhắn dạng text (JSON)
            if "text" in message:
                try:
                    data = json.loads(message["text"])
                    
                    # Lệnh bắt đầu ghi âm
                    if data.get("command") == "start_recording":
                        is_recording = True
                        await websocket.send_json({"type": "recording_started"})
                    
                    # Lệnh kết thúc ghi âm và xử lý
                    elif data.get("command") == "stop_recording":

                        # Save and convert audio for debugging
                        # debug_filename = save_audio_buffer_as_wav(audio_buffer)

                        is_recording = False
                        await gemini_live_stream(audio_buffer, websocket)
                        await websocket.send_json({"type": "recording_stopped"})

                        # Reset the audio buffer for the next recording
                        audio_buffer = io.BytesIO()
                        
                    # Cập nhật tham số
                    elif data.get("command") == "update_params":
                        if "model_id" in data:
                            model_id = data["model_id"]
                        if "voice" in data:
                            voice = data["voice"]
                        await websocket.send_json({"type": "params_updated"})
                    
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "Invalid JSON message"})
    
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        try:
            await websocket.close(code=1011, reason="Server error")
        except:
            pass