from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Callable
from deepgram import Deepgram
from dotenv import load_dotenv
import os
from typing import Optional, List, Literal, Dict, Any
from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, status, Body, Response
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime, timezone, timedelta
import uuid
import logging
import asyncio
import openai
import io
import json
import base64
from pydub import AudioSegment
from io import BytesIO

MAX_FILE_SIZE_MB = 50  # 50MB max file size
MAX_IMAGE_SIZE_MB = 20  # 20MB max image size
MAX_VIDEO_SIZE_MB = 100  # 100MB max video size
MAX_AUDIO_SIZE_MB = 25  # 25MB max audio size
MIN_BUFFER_THRESHOLD = 100
MAX_BUFFER_THRESHOLD = 250
SENTENCE_ENDINGS = (".", "?", "!", ":", ";", ",", "\n")

load_dotenv()
logger = logging.getLogger(__name__)
app = FastAPI()




@app.post("/mic", tags=["Audio"])
async def transcribe_audio_endpoint(
    audio: UploadFile = File(...),
    session: str = Form(...),
    current_user=Depends(get_current_user)
):
    """ Transcribe audio."""
    import math
    
    user_language = current_user.get("language", "en") if current_user else "vn"
    username = current_user["username"]
    start_time = datetime.now()
    trace_id = str(uuid.uuid4())
    
    try:
        # Check file size limit
        file_size_limit = 25 * 1024 * 1024  # 25MB
        audio_content = await audio.read()

        if len(audio_content) > file_size_limit:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail={
                "error_code": 413,
                "type_error": "dialog",
                "message": translate_error_message(f"Speech duration exceeds time limit", user_language)
            })
        
        # Check support content type and convert to wav if needed
        content_type = audio.content_type
        if content_type not in ["audio/wav", "audio/mp3", "audio/aac", "audio/flac", "audio/ogg", "audio/aiff"]:
            audio_content = convert_audio_to_wav(audio_content, content_type)
            content_type = "audio/wav"
        
        # Calculate duration of the audio file
        try: 
            audio_segment = AudioSegment.from_file(BytesIO(audio_content), format=content_type.split("/")[1])
            duration_seconds = len(audio_segment) / 1000  # Convert milliseconds to seconds
        except Exception as e:
            logger.error(f"Error processing audio file: {str(e)}")
            duration_seconds = None 
        
        # Convert audio to text
        transcribed_text, model_id = await speech2text(audio_content=audio_content, session=session, method="openai")
        
        # Calculate end time and usage cost
        end_time = datetime.now()

        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xử lý audio: {str(e)}")
        raise HTTPException(status_code=500, detail={
            "error_code": 500,
            "type_error": "dialog", 
            "message": translate_error_message(f"Lỗi khi xử lý âm thanh: {str(e)}", user_language)
        })

@app.websocket("/fastapi2/ws/speech-synthesis")
async def text2speech_stream(websocket: WebSocket):
    """Websocket API for text to speech synthesis real-time."""
    await websocket.accept()
    await websocket.send_json({"type": "connection_ready"})
    config = await websocket.receive_json()
    token = config.get("token")
    if not token:
        await websocket.close(code=4401, reason="Authentication required")
        return

    # Xác thực token
    try:
        current_user = await get_current_user(token)
    except Exception as e:
        await websocket.close(code=4403, reason="Authentication failed")
        return

    logger.info("WebSocket connection accepted for text-to-speech synthesis")

    try:
        text_chunk_queue = asyncio.Queue() # Queue for text chunks in order to synthesis
        audio_chunk_queue = asyncio.Queue() # Queue for audio chunks to send to client

        #Default parameters
        voice_character = "fable"
        voice_speed = 1.0
        session_id = None
        response_id = None

        # Recei initial configuration from client after button click
        config = await websocket.receive_json()

        # Get configuration parameters
        voice_character = config.get("voice_character", voice_character)
        voice_speed = config.get("voice_speed", voice_speed)
        session_id = config.get("session_id", None)
        response_id = config.get("response_id", None)
        username = config.get("username", None)

        # Flag to indicate if finish  stream
        text_stream_done = asyncio.Event()
        audio_processing_done = asyncio.Event()

        # Created audio URLs for tracking
        created_audio_urls = []

        # Buffer text to optimize TTS requests
        buffer_text = ""
        buffer_lock = asyncio.Lock()


        # ---- 1. Handle text streaming input from client ----
        async def text_receiver():
            nonlocal buffer_text

            try:
                full_text = ""
                
                while True:
                    # Receive text chunk from client 
                    message = await websocket.receive_json()

                    if "text" in message:
                        text_data = message["text"]

                        # Check if text finish 
                        if text_data == "[FINISH]":
                            # Xử lý buffer cuối cùng
                            async with buffer_lock:
                                if buffer_text:
                                    # Tách buffer thành các chunk theo câu
                                    for chunk in chunk_text_by_sentence(buffer_text, min_length=MIN_BUFFER_THRESHOLD, max_length=MAX_BUFFER_THRESHOLD):
                                        await text_chunk_queue.put(chunk)
                                    buffer_text = ""
                            await text_chunk_queue.put(None)
                            text_stream_done.set()
                            break

                        # Xử lý text chunk
                        async with buffer_lock:
                            buffer_text += text_data
                            full_text += text_data
                            
                            # Khi buffer đủ dài để có ít nhất một câu hoàn chỉnh
                            if len(buffer_text) >= MIN_BUFFER_THRESHOLD and any(ending in buffer_text for ending in SENTENCE_ENDINGS):
                                # Tách buffer thành các chunk theo câu
                                chunks = chunk_text_by_sentence(buffer_text, min_length=MIN_BUFFER_THRESHOLD, max_length=MAX_BUFFER_THRESHOLD)
                                
                                # Giữ lại phần cuối cùng nếu nó không kết thúc bằng dấu câu
                                if chunks and not any(buffer_text.strip().endswith(ending) for ending in SENTENCE_ENDINGS):
                                    buffer_text = chunks.pop()
                                else:
                                    buffer_text = ""
                                    
                                # Gửi các chunk đã tách được vào queue
                                for chunk in chunks:
                                    if chunk.strip():
                                        await text_chunk_queue.put(chunk)
                            
                            # Xử lý buffer quá dài, buộc phải cắt
                            elif len(buffer_text) >= MAX_BUFFER_THRESHOLD:
                                chunks = chunk_text_by_sentence(buffer_text, min_length=MIN_BUFFER_THRESHOLD, max_length=MAX_BUFFER_THRESHOLD)
                                
                                # Giữ lại phần cuối cùng cho buffer tiếp theo
                                if chunks:
                                    buffer_text = chunks.pop() if len(chunks) > 1 else ""
                                else:
                                    buffer_text = ""
                                    
                                # Gửi các chunk đã tách được vào queue
                                for chunk in chunks:
                                    if chunk.strip():
                                        await text_chunk_queue.put(chunk)
                    
                    elif "json" in message:
                        # Handle any additional commands or configuration sent as JSON
                        json_data = json.loads(message["json"])
                        if json_data.get("command") == "flush":
                            # Force flush remaining buffer
                            async with buffer_lock:
                                if buffer_text:
                                    # Tách buffer thành các chunk theo câu
                                    for chunk in chunk_text_by_sentence(buffer_text, min_length=MIN_BUFFER_THRESHOLD, max_length=MAX_BUFFER_THRESHOLD):
                                        if chunk.strip():
                                            await text_chunk_queue.put(chunk)
                                    buffer_text = ""
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected during text reception")
                # Ensure remaining text gets processed
                async with buffer_lock:
                    if buffer_text:
                        # Tách buffer thành các chunk theo câu
                        for chunk in chunk_text_by_sentence(buffer_text, min_length=MIN_BUFFER_THRESHOLD, max_length=MAX_BUFFER_THRESHOLD):
                            if chunk.strip():
                                await text_chunk_queue.put(chunk)
                await text_chunk_queue.put(None)
                text_stream_done.set()
            
            except Exception as e:
                logger.error(f"Error in text receiver: {str(e)}")
                await websocket.close(code=1011, reason="Server error")
                text_stream_done.set()
        

        # ---- 2. Handle audio synthesis and streaming ----
        async def tts_processor():
            current_chunk_id = 0
            from openai import AsyncOpenAI
            client = AsyncOpenAI()

            while True:
                # Get text chunk from queue
                text_chunk = await text_chunk_queue.get()

                if text_chunk is None:
                    await audio_chunk_queue.put(None) # Signal end of stream
                    audio_processing_done.set()
                    break
                
                try:
                    chunk_id = current_chunk_id
                    current_chunk_id += 1

                    try:
                        
                        request_params = {
                            "model": "gpt-4o-mini-tts",
                            "input": text_chunk,
                            "voice": voice_character,
                            "speed": voice_speed,
                            "response_format": "mp3"
                        }

                        # Thông báo bắt đầu xử lý
                        await audio_chunk_queue.put({
                            "chunk_id": chunk_id,
                            "type": "processing_start",
                            "streaming": True
                        })

                        # Tạo buffer để lưu toàn bộ audio
                        buffer = io.BytesIO()
                        streaming_chunk_count = 0


                        # Kiểm tra xem có sử dụng streaming API không
                        if client.audio.speech.with_streaming_response:
                            logger.info(f"Using streaming API for TTS with chunk {chunk_id}")
                        else:
                            logger.info(f"Using non-streaming API for TTS with chunk {chunk_id}")
                        # Dùng streaming API
                        response = client.audio.speech.with_streaming_response.create(**request_params)
                        async with response as streaming_response:
                            # Thông báo stream đã bắt đầu
                            await audio_chunk_queue.put({
                                "chunk_id": chunk_id,
                                "type": "stream_started",
                                "streaming": True,
                            })

                            # Bằng đoạn code này
                            i = 0
                            async for audio_bytes in streaming_response.iter_bytes(chunk_size=4096):
                                if not audio_bytes:
                                    continue
                                    
                                buffer.write(audio_bytes)
                                logger.info(f"Received audio chunk {i+1} for text chunk: {text_chunk}")
                                
                                # Put each audio chunk into queue
                                await audio_chunk_queue.put({
                                    "chunk_id": chunk_id,
                                    "streaming": True,
                                    "audio_content": audio_bytes,
                                    "chunk_index": i,
                                    "is_complete": False
                                })
                                streaming_chunk_count += 1
                                i += 1
                        
                        logger.info(f"Streaming completed for chunk {chunk_id} with {streaming_chunk_count} audio chunks")
                        
                        # Upload toàn bộ audio lên storage
                        buffer.seek(0)
                        audio_content = buffer.read()
                        file_name = f"{session_id}_{chunk_id}.mp3"

                        audio_url = await upload_file_to_minio(
                            file_data=audio_content,
                            file_name=file_name,
                            content_type="audio/mpeg",
                            bucket_name="audios",
                            is_secure=False,
                            is_downloadable=False
                        )

                        buffer.close()
                        del buffer

                        if audio_url:
                            created_audio_urls.append(audio_url)

                            # Thông báo streaming hoàn tất
                            await audio_chunk_queue.put({
                                "chunk_id": chunk_id,
                                "streaming": True,
                                "is_complete": True,
                                "audio_url": audio_url,
                                "audio_tag": f"<audio>{audio_url}</audio>"
                            })
                        

                    except Exception as streaming_error:
                        # If streaming fails, fallback to non-streaming TTS
                        logger.warning(f"Streaming failed for chunk {chunk_id}: {str(streaming_error)}. Falling back to non-streaming TTS.")

                        # Thông báo chuyển sang non-streaming
                        await audio_chunk_queue.put({
                            "chunk_id": chunk_id,
                            "type": "fallback_to_non_streaming"
                        })

                        # # Sử dụng non-streaming TTS
                        # audio_result = await text_to_speech(
                        #     text=text_chunk,
                        #     voice=voice_character,
                        #     speed=voice_speed
                        # )

                        audio_content = await text2speech(
                            text= text_chunk,
                            voice=voice_character,
                            speed=voice_speed
                        )

                        file_name = f"{session_id}_{chunk_id}.mp3"

                        if audio_content:
                            audio_url = await upload_file_to_minio(
                                file_data=audio_content,
                                file_name=file_name,
                                content_type="audio/mpeg",
                                bucket_name="audios",
                                is_secure=False,
                                is_downloadable=False
                            )
                            created_audio_urls.append(audio_url)

                            # Put audio chunk into queue
                            await audio_chunk_queue.put({
                                "chunk_id": chunk_id,
                                "audio_content": audio_content,
                                "audio_tag": f"<audio>{audio_url}</audio>",
                                "streaming": False,
                                "is_complete": True
                            })
                        else:
                            logger.error(f"TTS failed for chunk: {text_chunk}")
                            await websocket.send_json({
                                "type": "error",
                                "message": f"Failed to synthesize audio for chunk {chunk_id}",
                            })
                except Exception as e:
                    logger.error(f"Error processing TTS: {str(e)}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Error processing TTS: {str(e)}"
                    })

                finally:
                    # Mark task as done
                    text_chunk_queue.task_done()


        # ---- 3. Send audio streaming to client ----            
        async def audio_sender():
            # Theo dõi các audio chunk hiện đang xử lý
            active_chunks = {}
            
            while True:
                # Lấy audio chunk từ queue
                audio_chunk = await audio_chunk_queue.get()

                if audio_chunk is None:
                    # End of stream signal
                    await websocket.send_json({"type": "end_stream"})
                    break
                
                try:
                    chunk_id = audio_chunk.get("chunk_id")
                    
                    # Xử lý thông báo trạng thái
                    if "type" in audio_chunk:
                        if audio_chunk["type"] == "processing_started":
                            await websocket.send_json({
                                "type": "processing_started",
                                "chunk_id": chunk_id,
                                "text": audio_chunk.get("text", "")
                            })
                            audio_chunk_queue.task_done()  # Đánh dấu task hoàn thành
                            continue
                            
                        elif audio_chunk["type"] == "stream_started":
                            # Khởi tạo tracking cho chunk mới
                            active_chunks[chunk_id] = {
                                "status": "streaming",
                                "parts": []
                            }
                            
                            # Thông báo client để chuẩn bị nhận stream
                            await websocket.send_json({
                                "type": "audio_begin",
                                "chunk_id": chunk_id,
                                "streaming": True
                            })
                            audio_chunk_queue.task_done()  # Đánh dấu task hoàn thành
                            continue
                            
                        elif audio_chunk["type"] == "fallback_to_non_streaming":
                            # Thông báo client về việc chuyển sang non-streaming
                            if chunk_id in active_chunks:
                                # Dọn dẹp state của streaming trước đó nếu có
                                del active_chunks[chunk_id]
                            
                            await websocket.send_json({
                                "type": "fallback_to_non_streaming",
                                "chunk_id": chunk_id
                            })
                            audio_chunk_queue.task_done()  # Đánh dấu task hoàn thành
                            continue
                    else:
                        # Xử lý audio data
                        streaming = audio_chunk.get("streaming", False)
                        is_complete = audio_chunk.get("is_complete", False)
                        
                        if streaming:
                            logger.info(f"Sending audio chunk {chunk_id} to client in streaming mode")
                            # Streaming mode - gửi từng phần audio
                            if not is_complete:
                                # Gửi audio chunk dạng base64
                                audio_content = audio_chunk["audio_content"]
                                await websocket.send_json({
                                    "type": "audio_chunk",
                                    "chunk_id": chunk_id,
                                    "chunk_index": audio_chunk.get("chunk_index", 0),
                                    "audio_content": base64.b64encode(audio_content).decode(),
                                    "is_complete": False
                                })
                                
                                # Thêm vào tracking
                                if chunk_id in active_chunks:
                                    active_chunks[chunk_id]["parts"].append(audio_chunk.get("chunk_index", 0))
                            else:
                                # Streaming hoàn tất - gửi URL cuối cùng
                                await websocket.send_json({
                                    "type": "audio_complete",
                                    "chunk_id": chunk_id,
                                    "audio_url": audio_chunk["audio_url"],
                                    "audio_tag": audio_chunk["audio_tag"]
                                })
                                
                                # Xóa khỏi tracking
                                if chunk_id in active_chunks:
                                    del active_chunks[chunk_id]
                        else:
                            # Non-streaming mode - gửi toàn bộ audio một lần
                            logger.info(f"Sending non-streaming audio chunk {chunk_id} to client")
                            
                            # Gửi audio dạng base64
                            audio_content = audio_chunk["audio_content"]
                            await websocket.send_json({
                                "type": "audio_chunk",
                                "chunk_id": chunk_id,
                                "audio_content": base64.b64encode(audio_content).decode(),
                                "audio_url": audio_chunk.get("audio_url", ""),
                                "audio_tag": audio_chunk.get("audio_tag", ""),
                                "is_complete": True,
                                "streaming": False
                            })
                            pass
                        
                        # Đợi xác nhận từ client nếu cần
                        try:
                            # Chỉ đợi xác nhận cho các chunk hoàn chỉnh
                            if is_complete or not streaming:
                                ack = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
                                if ack.get("type") == "ack" and ack.get("chunk_id") == chunk_id:
                                    logger.info(f"Client acknowledged chunk {chunk_id}")
                                else:
                                    logger.warning(f"Unexpected ack format: {ack}")
                        except asyncio.TimeoutError:
                            logger.warning(f"Client acknowledgment timeout for chunk {chunk_id}")
                        
                except WebSocketDisconnect:
                    logger.info("WebSocket disconnected during audio sending")
                    break
                except Exception as e:
                    logger.error(f"Error sending audio chunk: {str(e)}")
                
                # Đánh dấu task hoàn thành
                audio_chunk_queue.task_done()

        # ---4. Start all tasks
        # Create tasks for text receiver, TTS processor and audio sender
        text_receiver_task = asyncio.create_task(text_receiver())
        tts_processor_task = asyncio.create_task(tts_processor())
        audio_sender_task = asyncio.create_task(audio_sender())

        # Wait for all tasks to complete
        await text_stream_done.wait()
        await audio_processing_done.wait()

        # Ensure all queues are fully processed
        await asyncio.gather(
            text_receiver_task,
            tts_processor_task,
            audio_sender_task,
            return_exceptions=True
        )

        # ---5. Save audio to database if needed
        if session_id and response_id and created_audio_urls:
            # audio_tags = [f"<audio>{url}</audio>" for url in created_audio_urls]
            pass

        # ---6. Final completion message
        await websocket.send_json({
            "type": "complete",
            "message": "Text-to-speech synthesis completed successfully",
        })
        await websocket.close()  # Đóng kết nối websocket khi hoàn thành

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected during TTS processing")
    except Exception as e:
        logger.error(f"WebSocket error during TTS processing: {str(e)}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Server error: {str(e)}"
            }) 
            await websocket.close(code=1011, reason="Server error")
        except:
            logger.error("Failed to close WebSocket connection after error")
            pass