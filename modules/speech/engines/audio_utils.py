from fastapi import WebSocket, WebSocketDisconnect
import base64
import asyncio
import io
import json
import re
import uuid
import logging
import time
import os
from openai import AsyncOpenAI, OpenAI

from V2_chat.controller.speech.engines.stt import speech2text
from V2_chat.controller.speech.engines.tts import text2speech
from V2_chat.controller.chat import chat_llm, translate_error_message, initialize_session, check_if_session_exists, save_pre_conversation
from V2_chat.controller.utils import normalize_http_exception, upload_file_to_minio

# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

async def _handle_stop_recording(
    websocket: WebSocket,
    audio_buffer: io.BytesIO,
    *,
    session_id: str,
    parent_response_id: str = None,
    model_id: str,
    voice: str,
    project_id: str = None,
    user_language: str,
    username: str,
    user_response_id: str,
    assistant_response_id: str,
    is_new: bool,
    current_user: dict = None,
):
    """Transcribe → LLM → TTS."""

    raw_audio = audio_buffer.getvalue()
    if not raw_audio:
        await websocket.send_json({"type": "error", "message": "No audio data received"})
        return

    await websocket.send_json({"type": "processing", "message": "Processing audio..."})

    # --------------------- 1. Speech‑to‑Text ------------------------
    try:
        transcription, _ = await speech2text(audio_content=raw_audio, method="gemini")
    except Exception as e:
        logger.warning(f"STT failure: {str(e)}")
        await websocket.send_json({"type": "error", "message": translate_error_message("Failed to transcribe audio", user_language)})
        return

    if not transcription:
        await websocket.send_json({"type": "error", "message": translate_error_message("Empty transcription", user_language)})
        return

    await websocket.send_json({"type": "transcription", "text": transcription})

    # --- Prepare OpenAI TTS client once for reuse ---
    openai_client = OpenAI()
    
    BUFFER_THRESHOLD = 400  # Giảm ngưỡng để xử lý sớm hơn

    # Queue mới cho text cần TTS
    text_chunk_queue = asyncio.Queue()
    audio_chunk_queue = asyncio.Queue()
    client_ack_queue = asyncio.Queue[int]()

    buffer_text = ""
    buffer_lock = asyncio.Lock()
    llm_done = asyncio.Event()
    chunk_id_counter = 0

    async def llm_chunk_receiver():
        nonlocal buffer_text
        await websocket.send_json({"type": "thinking", "message": "Generating response..."})
        try:
            async for raw in chat_llm(
               question=transcription,
                session=session_id,
                modelId=model_id,
                parentResponseId=parent_response_id,
                project_id=project_id,
                username=username,
                system_prompt=current_user.get("system_prompt", "default"),
                file_content=None,
                current_user=current_user,
                userResponseID=user_response_id,
                assistantResponseID=assistant_response_id,
                is_new_conversation=is_new,
            ):
                # Extract the text piece
                if isinstance(raw, bytes):
                    try:
                        payload = json.loads(raw.decode())
                        piece = payload.get("response", {}).get("chunk", "")
                    except Exception:
                        piece = raw.decode(errors="ignore")
                else:
                    piece = raw.get("response", {}).get("chunk", "")

                if not piece or piece in ("<answer>", "</answer>") or piece.startswith("<model>"):
                    continue

                await websocket.send_json({"type": "text_chunk", "text": piece})

                async with buffer_lock:
                    buffer_text += piece
                    # Khi đủ điều kiện, đưa text vào queue để TTS song song
                    if (len(buffer_text) >= BUFFER_THRESHOLD or 
                        buffer_text.endswith((".", "?")) or 
                        (len(buffer_text) > 0 and llm_done.is_set())):
                        
                        text_to_convert = buffer_text
                        buffer_text = ""
                        # Đưa vào queue để xử lý song song
                        await text_chunk_queue.put(text_to_convert)
        except Exception as e:
            logger.error(f"LLM error: {str(e)}")
            await websocket.send_json({
                "type": "error",
                "message": translate_error_message("Error generating response", user_language)
            })
        finally:
            llm_done.set()
            # Đảm bảo phát hết buffer cuối cùng
            async with buffer_lock:
                if buffer_text:
                    await text_chunk_queue.put(buffer_text)
            # Đánh dấu kết thúc queue
            await text_chunk_queue.put(None)

    # Coroutine mới xử lý TTS song song
    async def tts_processor():
        nonlocal chunk_id_counter
        while True:
            text = await text_chunk_queue.get()
            if text is None:  # End signal
                await audio_chunk_queue.put(None)
                break
                
            try:
                current_chunk_id = chunk_id_counter
                chunk_id_counter += 1
                
                # TTS processing
                if model_id and str(model_id).lower().startswith("gemini"):
                    from V2_chat.controller.speech.engines.tts import _gemini_tts
                    audio_bytes = await _gemini_tts(text, voice="Kore")
                    if audio_bytes:
                        await audio_chunk_queue.put({
                            "audio_bytes": audio_bytes,
                            "chunk_id": current_chunk_id
                        })
                    else:
                        logger.warning(f"Gemini TTS returned no audio for chunk {current_chunk_id}")
                else:
                    # Đưa text vào queue để OpenAI xử lý trong audio_sender
                    await audio_chunk_queue.put({
                        "text": text,
                        "chunk_id": current_chunk_id
                    })
            except Exception as e:
                logger.warning(f"TTS conversion error: {str(e)}")
    
    async def audio_sender():
        audio_segment_processing = asyncio.Semaphore(1)  # Ensure only one segment is processed at a time
        last_chunk_id = -1
        
        while True:
            chunk_data = await audio_chunk_queue.get()
            if chunk_data is None:  # End of processing
                break
                
            chunk_id = chunk_data["chunk_id"]
            
            # Đợi client xác nhận đã phát hết audio trước
            if last_chunk_id >= 0:
                await websocket.send_json({
                    "type": "audio_await_previous",
                    "wait_for_chunk_id": last_chunk_id
                })
                
                try:
                    ack_chunk_id = await asyncio.wait_for(client_ack_queue.get(), timeout=0.2)
                    if ack_chunk_id != last_chunk_id:
                        logger.warning(f"Client ack mismatch: expected {last_chunk_id}, got {ack_chunk_id}")
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for client ack for chunk {last_chunk_id}")
                    
            async with audio_segment_processing:
                await websocket.send_json({
                    "type": "audio_stream_begin",
                    "chunk_id": chunk_id,
                    "format": "mp3"
                })
                
                try:
                    if "audio_bytes" in chunk_data:  # Đã convert từ Gemini
                        audio_bytes = chunk_data["audio_bytes"]
                        b64 = base64.b64encode(audio_bytes).decode()
                        logger.info(f"Sending audio chunk {chunk_id} of length {len(audio_bytes)} bytes")
                        await websocket.send_json({
                            "type": "audio_chunk",
                            "chunk": b64,
                            "chunk_id": chunk_id,
                        })
                    else:  # Cần convert bằng OpenAI
                        text = chunk_data["text"]
                        tts_client = openai_client.audio.speech.with_streaming_response
                        tts_params = {
                            "model": "gpt-4o-mini-tts",
                            "input": text,
                            "voice": voice,
                            "response_format": "mp3",
                            "speed": 1.0,
                        }
                        
                        with tts_client.create(**tts_params) as resp:
                            for audio_bytes in resp.iter_bytes(chunk_size=4096):
                                if not audio_bytes:
                                    continue
                                b64 = base64.b64encode(audio_bytes).decode()
                                await websocket.send_json({
                                    "type": "audio_chunk",
                                    "chunk": b64,
                                    "chunk_id": chunk_id,
                                })
                except Exception as e:
                    logger.warning(f"Audio sending error: {str(e)}")
                    await websocket.send_json({
                        "type": "error",
                        "message": translate_error_message("TTS streaming failed", user_language)
                    })
                    return
                    
                await websocket.send_json({
                    "type": "audio_stream_end",
                    "chunk_id": chunk_id
                })
                
                last_chunk_id = chunk_id

    async def client_message_handler():
        try:
            while True:
                message = await websocket.receive_json()
                if message.get("type") == "audio_played":
                    chunk_id = message.get("chunk_id")
                    if chunk_id is not None:
                        await client_ack_queue.put(chunk_id)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning(f"Error processing client message: {str(e)}")

    # Chạy tất cả các coroutines
    await asyncio.gather(
        llm_chunk_receiver(),
        tts_processor(),  
        audio_sender(),
        client_message_handler(),
    )