import os
import logging
import json
import asyncio
import io 
import uuid
from datetime import datetime
from fastapi import FastAPI, Request, WebSocket, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import Dict, Callable, Any
from dotenv import load_dotenv
from starlette.websockets import WebSocketDisconnect

from controller.speech.meeting.meeting_minutes import process_audio
from controller.speech.live.server import gemini_live_stream, GeminiLiveSession
from controller.speech.audio_format import save_audio_buffer_as_wav, convert_to_raw_pcm
from controller.speech.live.server_adk import start_agent_session, agent_to_client_messaging, client_to_agent_messaging
load_dotenv()

router = APIRouter()
logger = logging.getLogger("deepgram")
templates = Jinja2Templates(directory="templates")
 
@router.get("/", response_class=HTMLResponse)
def get(request: Request):
    return templates.TemplateResponse("meeting.html", {"request": request})


@router.websocket("/meeting")
async def websocket_meeting(websocket: WebSocket):
    logger.info("WebSocket connection attempt")
    await websocket.accept()
    # Generate or retrieve a session ID
    session_id = f"meeting_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    # Attach it to the websocket object for reference
    websocket.session_id = session_id

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





# @app.websocket("/ws/live")
# async def voice_chat_websocket(websocket: WebSocket):
#     """WebSocket endpoint for voice chat with authentication and session management."""
    
#     model_id = "gemini-2.5-flash-preview-native-audio-dialog"
#     voice = "alloy"
#     session_id = str(uuid.uuid4())
#     parent_response_id = None
#     project_id = None
#     current_user = None
#     user_language = "en"

#     # 1. Khởi tạo session ngay từ đầu
#     gemini_session = GeminiLiveSession(
#         websocket,
#         model="gemini-2.5-flash-preview-native-audio-dialog",
#         session_id=session_id,  # hoặc nhận từ client
#     )
    
    
#     try:
#         # Chấp nhận kết nối WebSocket
#         await websocket.accept()
#         logger.info("WebSocket connection accepted")
        
#         # Nhận dữ liệu xác thực từ client
#         auth_data = await websocket.receive_json()
        
#         # Gửi thông báo xác thực thành công
#         await websocket.send_json({"type": "connection_ready", "message": "Authentication successful"})

#         #Setup continous streaming
#         await gemini_session.setup_continuous_stream()

#         # Xử lý tin nhắn từ client
#         while True:
#             message = await websocket.receive()
            
#             # ==== AUDIO FRAME ====
#             msg_bytes = message.get("bytes")
#             if msg_bytes is not None:
#                 try:
#                     await gemini_session.process_audio_chunk(msg_bytes)
#                 except Exception as e:
#                     logger.warning(f"Error processing audio chunk: {e}")
#                 continue

#             # ==== JSON COMMAND ====
#             msg_text = message.get("text")
#             if msg_text is not None:
#                 try:
#                     data = json.loads(msg_text)
#                     cmd = data.get("command")
#                     if cmd == "pause_streaming":
#                         await gemini_session.pause_streaming()
#                         await websocket.send_json({"type": "streaming_paused"})
#                     elif cmd == "resume_streaming":
#                         await gemini_session.resume_streaming()
#                         await websocket.send_json({"type": "streaming_resumed"})
#                     elif cmd == "disconnect":
#                         await gemini_session.end_streaming()
#                         await gemini_session.save_conversation()
#                         await websocket.send_json({"type":"disconnect_ack"})
#                         break
#                     elif cmd == "update_params":
#                         if "model_id" in data:
#                             gemini_session.model = data["model_id"]
#                         if "voice" in data:
#                             # nếu voice cần đẩy vào config, cập nhật ở gemini_session.config
#                             pass
#                         await websocket.send_json({"type":"params_updated"})
#                     elif cmd == "client_ack":
#                         pass  # (optional) áp dụng back-pressure
#                 except json.JSONDecodeError:
#                     await websocket.send_json({"type":"error","message":"Invalid JSON"})
    
#     except WebSocketDisconnect:
#         logger.info("WebSocket disconnected")
#         await gemini_session.end_streaming()
#     except Exception as e:
#         logger.error(f"WebSocket error: {str(e)}")
#         try:
#             await gemini_session.end_streaming()
#             await websocket.close(code=1011, reason="Server error")
#         except:
#             pass
#     finally:
#         # Ensure websocket is closed
#         if websocket.client_state.name == 'CONNECTED':
#             await websocket.close()



@router.websocket("/ws/live/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, is_audio: str, voice: str = "Kore"):
    """Client websocket endpoint"""

    # Wait for client connection
    await websocket.accept()
    print(f"Client #{user_id} connected, audio mode: {is_audio}")

    # Start agent session
    user_id_str = str(user_id)
    live_events, live_request_queue = await start_agent_session(user_id_str, is_audio == "true", voice=voice)

    # Start tasks
    agent_to_client_task = asyncio.create_task(
        agent_to_client_messaging(websocket, live_events)
    )
    client_to_agent_task = asyncio.create_task(
        client_to_agent_messaging(websocket, live_request_queue)
    )

    # Wait until the websocket is disconnected or an error occurs
    tasks = [agent_to_client_task, client_to_agent_task]
    await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

    # Close LiveRequestQueue
    live_request_queue.close()

    # Disconnected
    print(f"Client #{user_id} disconnected")