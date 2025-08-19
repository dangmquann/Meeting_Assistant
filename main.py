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
from modules.speech.live.live_gemini import gemini_live_stream, GeminiLiveSession
from modules.speech.audio_format import save_audio_buffer_as_wav, convert_to_raw_pcm
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





@app.websocket("/ws/voice-chat")
async def voice_chat_websocket(websocket: WebSocket):
    """WebSocket endpoint for voice chat with authentication and session management."""
    
    model_id = "gemini-2.5-flash-preview-native-audio-dialog"
    voice = "alloy"
    session_id = None
    parent_response_id = None
    project_id = None
    current_user = None
    user_language = "en"

    # 1. Khởi tạo session ngay từ đầu
    gemini_session = GeminiLiveSession(
        websocket,
        model="gemini-2.5-flash-preview-native-audio-dialog",
        session_id=str(uuid.uuid4()),  # hoặc nhận từ client
    )
    

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
            
             # ====== AUDIO FRAMES ======
            if "bytes" in message and message["bytes"] is not None:
                if is_recording:
                    audio_buffer.write(message["bytes"])
                continue
            
           # ====== TEXT FRAMES (JSON) ======
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

                        # is_recording = False
                        # await gemini_live_stream(audio_buffer, websocket)
                        await gemini_session.setup()
                        is_recording = False
                        audio_buffer.seek(0)

                        try:
                            processed_audio = convert_to_raw_pcm(audio_buffer)
                            print(f"[DEBUG] PCM conversion successful. Processed audio length: {len(processed_audio)} bytes")
                            
                        except Exception as e:
                            logger.warning(f"Could not convert audio, using original audio: {e}")
                            processed_audio = audio_buffer.getvalue()
                        print(f"[DEBUG] Final audio to be sent to Gemini: {len(processed_audio)} bytes")

                        await gemini_session.send_audio(processed_audio)

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
                    
                    elif data.get("command") == "disconnect":
                        logger.info(f"Client requested disconnection for session: {session_id}")
                        await gemini_session.save_conversation()  
                        
                        # Send acknowledgement to client
                        await websocket.send_json({
                            "type": "disconnect_ack", 
                            "message": "Session ended and conversation saved"
                        })
                        
                        # End the loop to close the connection
                        break
                    
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
    finally:
        # Đảm bảo đóng websocket khi kết thúc
        if websocket.client_state.name == 'CONNECTED':
            await websocket.close()