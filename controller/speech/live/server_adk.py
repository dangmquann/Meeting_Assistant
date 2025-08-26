import json
import base64
import warnings
from google.genai.types import (
    Part,
    Content,
    Blob,
)
import uuid
import asyncio
from datetime import datetime
from loguru import logger
from google.adk.runners import InMemoryRunner
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from google.genai import types
from google.adk.sessions import DatabaseSessionService
from fastapi import WebSocketDisconnect
from controller.speech.live.agent import root_agent
from controller.history_database import responseModel, insert_response


warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

APP_NAME = "Voice Assistant"


async def start_agent_session(user_id, session_id, is_audio=False, voice="Kore"):
    """Starts an agent session"""

    # Create a Runner
    runner = InMemoryRunner(
        app_name=APP_NAME,
        agent=root_agent,
    )

    # Create a Session
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,  # Replace with actual user ID
    )

    # Set response modality
    modality = "AUDIO" if is_audio else "TEXT"
    if is_audio:
        voice_config = types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfigDict(
                voice_name=voice
            )
        )
        speech_config = types.SpeechConfig(voice_config=voice_config)
        run_config = RunConfig(
            response_modalities=[modality],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=speech_config,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig()
        )
    else:
        run_config = RunConfig(
            response_modalities=[modality],
            session_resumption=types.SessionResumptionConfig(),
        )

    # Create a LiveRequestQueue for this session
    live_request_queue = LiveRequestQueue()

    # Start agent session
    live_events = runner.run_live(
        session=session,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    return live_events, live_request_queue


async def agent_to_client_messaging(websocket, live_events, persistence_context=None):
    """Agent to client communication"""

    # Initialize accumulation for assistant reponses
    accumulated_answer = ""
    accumulated_user_input = ""
    is_turn_complete = False
    user_time_out = None

    # Get information from persistence context if available
    session = persistence_context.get("session", None) if persistence_context else None
    current_assistant_response_id = persistence_context.get("current_assistant_response_id", None) if persistence_context else None
    current_user_input_id = None

    # Tạo ID mới cho phản hồi của trợ lí nếu chưa có
    if not current_assistant_response_id:
        current_assistant_response_id = str(uuid.uuid4())
        if persistence_context:
            persistence_context["current_assistant_response_id"] = current_assistant_response_id

    async def save_accumulated_user_input():
        """Lưu input tích lũy của người dùng vào database"""
        nonlocal accumulated_user_input, current_user_input_id
        
        if accumulated_user_input and session and persistence_context:
            try:
                if not current_user_input_id:
                    current_user_input_id = str(uuid.uuid4())
                
                parent_id = persistence_context.get("last_assistant_response_id", None)
                markdown_content = f"**Role:** User\n**Content:** {accumulated_user_input}"
                
                user_response = responseModel(
                    responseId=current_user_input_id,
                    sender="human",
                    message=accumulated_user_input,
                    session=session,
                    files=[],
                    citations=[],
                    createdAt=datetime.now().isoformat(),
                    modelId="gemini-live",
                    parentResponseId=parent_id,
                    markdown_content=markdown_content,
                )
                
                insert_response(user_response)
                persistence_context["current_user_response_id"] = current_user_input_id
                
                logger.info(f"Saved accumulated user audio message: {current_user_input_id}")
                
                # Reset for next input
                accumulated_user_input = ""
                current_user_input_id = None
                
            except Exception as e:
                logger.error(f"Error saving accumulated user audio message: {e}")

    async for event in live_events:

        # If the turn complete or interrupted, send it
        if event.turn_complete or event.interrupted:
            # Lưu input người dùng đã tích lũy nếu còn
            if accumulated_user_input:
                await save_accumulated_user_input()

            # Lưu phản hồi vào database nếu có nội dung
            if accumulated_answer and session and persistence_context:
                user_response_id = persistence_context.get("current_user_response_id", None)

                try:
                    # Tạo nội dung markdown 
                    markdown_content = f"**Role:** Assistant\n**Content:** {accumulated_answer}"

                    # Tạo đối tượng phản hồi của trợ lí
                    assistant_response = responseModel(
                        responseId = current_assistant_response_id,
                        sender = "assistant",
                        message = accumulated_answer,
                        session = session,
                        files=[],
                        citations=[],
                        createdAt = datetime.now().isoformat(),
                        modelId="gemini-live",
                        parentResponseId=user_response_id,
                        markdown_content=markdown_content,
                    )

                    # Lưu vào database
                    insert_response(assistant_response)

                    # Cập nhật context với ID phản hồi mới nhất 
                    persistence_context["last_assistant_response_id"] = current_assistant_response_id
                    logger.info(f"Saved assistant response to database: {current_assistant_response_id}")

                    # Đánh dấu đã hoàn thành để chuẩn bị cho lượt tiếp theo
                    is_turn_complete = True

                    # Reset accumulated answer for the next turn
                    accumulated_answer = ""
                    persistence_context["current_assistant_response_id"] = None 

                except Exception as e:
                    logger.error(f"Error saving response: {e}")

            message = {
                "turn_complete": event.turn_complete,
                "interrupted": event.interrupted,
            }
            await websocket.send_text(json.dumps(message))
            logger.info(f"[AGENT TO CLIENT]: {message}")
            continue

        # Read the Content and its first Part
        part: Part = (
            event.content and event.content.parts and event.content.parts[0]
        )
        if not part:
            continue

        # Collect user input texts (do not forward them as model outputs)
        role = getattr(event.content, "role", None)
        if role == "user" and getattr(part, "text", None):
            notify = {
                "mime_type": "text/plain",
                "data": part.text,
                "role": "user",
            }
            await websocket.send_text(json.dumps(notify))
            print(f"[INPUT TEXTS]: {part.text}")

            # Accumulate user input texts
            accumulated_user_input += part.text
            # Hủy timeout cũ nếu có và đặt timeout mới để lưu input
            # if user_input_timeout:
            #     user_input_timeout.cancel()
            
            # # Đặt timeout 1.5 giây sau đó lưu input tích lũy vào database
            # # Giả định rằng khoảng cách > 1.5s giữa các đoạn là kết thúc một câu nói
            # user_input_timeout = asyncio.create_task(
            #     asyncio.sleep(1.5)
            # )
            # try:
            #     await user_input_timeout
            #     # Nếu đến đây, nghĩa là timeout đã kết thúc mà không bị hủy
            #     await save_accumulated_user_input()
            # except asyncio.CancelledError:
            #     # Timeout bị hủy do có input mới
            #     pass
                
            continue


        # If it's audio, send Base64 encoded audio data
        is_audio = part.inline_data and part.inline_data.mime_type.startswith("audio/pcm")
        if is_audio:
            audio_data = part.inline_data and part.inline_data.data
            if audio_data:
                message = {
                    "mime_type": "audio/pcm",
                    "data": base64.b64encode(audio_data).decode("ascii")
                }
                await websocket.send_text(json.dumps(message))
                print(f"[AGENT TO CLIENT]: audio/pcm: {len(audio_data)} bytes.")
                continue

        # If it's text and a partial text, send it
        if part.text and event.partial:
            message = {
                "mime_type": "text/plain",
                "data": part.text
            }
            await websocket.send_text(json.dumps(message))

            if is_turn_complete:
                current_assistant_response_id = str(uuid.uuid4())
                if persistence_context:
                    persistence_context["current_assistant_response_id"] = current_assistant_response_id
                is_turn_complete = False
            
            # Accumulate the text
            accumulated_answer += part.text
            print(f"[AGENT TO CLIENT]: text/plain: {message}")


async def client_to_agent_messaging(websocket, live_request_queue, persistence_context=None):
    """Client to agent communication"""
    # Lấy thông tin từ persistence_context
    session = persistence_context.get("session", None) if persistence_context else None
    last_assistant_response_id = persistence_context.get("last_assistant_response_id", None) if persistence_context else None

    try:
        while True:
            # Decode JSON message
            message_json = await websocket.receive_text()
            message = json.loads(message_json)
            mime_type = message["mime_type"]
            data = message["data"]

            # Send the message to the agent
            if mime_type == "text/plain":
                # Lưu tin nhắn text trực tiếp từ client vào database
                if session and persistence_context:
                    try:
                        # Tạo ID phản hồi mới cho người dùng
                        user_response_id = str(uuid.uuid4())
                        
                        # Tạo markdown content
                        markdown_content = f"**Role:** User\n**Content:** {data}"
                        
                        # Tạo đối tượng phản hồi người dùng
                        user_response = responseModel(
                            responseId=user_response_id,
                            sender="human",
                            message=data,
                            session=session,
                            files=[],
                            citations=[],
                            createdAt=datetime.now().isoformat(),
                            modelId="gemini-live",
                            parentResponseId=last_assistant_response_id,
                            markdown_content=markdown_content
                        )
                        
                        # Lưu vào database
                        insert_response(user_response)
                        
                        # Cập nhật ID cho phản hồi tiếp theo
                        persistence_context["current_user_response_id"] = user_response_id
                    except WebSocketDisconnect:
                        logger.warning("WebSocket disconnected while saving user text message.")
                        break
                    except Exception as e:
                        logger.error(f"Error saving user text message: {e}")

                # Send a text message
                content = Content(role="user", parts=[Part.from_text(text=data)])
                live_request_queue.send_content(content=content)
                print(f"[CLIENT TO AGENT]: {data}")
            elif mime_type == "audio/pcm":
                # Send an audio data
                decoded_data = base64.b64decode(data)
                live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
            else:
                raise ValueError(f"Mime type not supported: {mime_type}")
    except Exception as e:
        logger.error(f"Error in client_to_agent_messaging: {e}")