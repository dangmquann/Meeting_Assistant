import asyncio 
import io
import base64
import logging
import datetime
import uuid
import os
from google import genai 
from google.genai import types
from fastapi import WebSocket, WebSocketDisconnect

from V2_chat.controller.speech.audio_format import pcm_to_wav_bytes, convert_to_raw_pcm

logger = logging.getLogger("live_gemini")

class GeminiLiveSession:
    def __init__(
        self, 
        websocket, 
        model="gemini-2.5-flash-preview-native-audio-dialog", 
        session_id=None,
        username=None,
        user_response_id=None
    ):
        self.websocket = websocket
        self.model = model
        self.session_id = session_id
        self.username = username
        self.user_response_id = user_response_id
        self.chunk_id = 0
        self.gemini_response_queue = asyncio.Queue()
        self.client = genai.Client()
        
        # Cấu hình cho Gemini
        self.config = {
            "response_modalities": ["AUDIO"],
            "system_instruction": (
                "Your name is Caimio, a helpful voice assistant created by HorusAI. "
                "Always refer to yourself as Caimio when talking to users. "
                "You answer in a friendly, conversational tone and speak naturally."
            ),
            "realtime_input_config": {
                "automatic_activity_detection": {
                    "disabled": False,
                    "start_of_speech_sensitivity": types.StartSensitivity.START_SENSITIVITY_LOW,
                    "end_of_speech_sensitivity": types.EndSensitivity.END_SENSITIVITY_LOW,
                    "prefix_padding_ms": 20,
                    "silence_duration_ms": 100,
                }
            }
        }
    
    async def setup(self):
        """Chuẩn bị phiên làm việc và thông báo cho client."""
        logger.debug("Setting up Gemini Live session")
        await self.websocket.send_json({
            "type": "processing",
            "message": "Processing your request..."
        })
        
    async def send_audio(self, processed_audio):
        """Gửi audio đến Gemini API và xử lý phản hồi."""
        try:
            logger.info("Starting Gemini Live API connection")
            async with self.client.aio.live.connect(model=self.model, config=self.config) as session:
                # Gửi audio tới Gemini
                await session.send_realtime_input(
                    audio=types.Blob(data=processed_audio, mime_type="audio/pcm;rate=16000")
                )
                await session.send_realtime_input(audio_stream_end=True)
                logger.info("Audio sent to Gemini Live API")
                
                # Xử lý phản hồi
                await asyncio.gather(
                    self._receive_responses(session),
                    self._send_audio_chunks()
                )
                
        except Exception as e:
            logger.error(f"Error in send_audio: {e}")
            if self.websocket.client_state.name == 'CONNECTED':
                await self.websocket.send_json({
                    "type": "error",
                    "message": f"An error occurred: {str(e)}"
                })
    
    async def _receive_responses(self, session):
        """Nhận audio từ Gemini và đưa vào queue."""
        try:
            async for response in session.receive():
                if response.data:
                    await self.gemini_response_queue.put(response.data)
                # Giữ an toàn khi truy cập thuộc tính server_content
                if response.server_content and response.server_content.model_turn is not None:
                    logger.debug(f"Response format: {response.server_content.model_turn.parts[0].inline_data.mime_type}")
        except Exception as e:
            logger.error(f"Error receiving from Gemini: {e}")
        finally:
            # Báo hiệu kết thúc luồng
            await self.gemini_response_queue.put(None)
    
    async def _send_audio_chunks(self):
        """Gửi audio chunks tới client."""
        chunk_id = 0
        try:
            while True:
                audio_data = await self.gemini_response_queue.get()
                if audio_data is None:
                    break
                
                # Chuyển đổi PCM sang WAV bytes
                audio_data = pcm_to_wav_bytes(audio_data)
                
                # Mã hóa và gửi audio chunk
                audio_b64 = base64.b64encode(audio_data).decode()
                await self.websocket.send_json({
                    "type": "audio_chunk",
                    "chunk": audio_b64,
                    "chunk_id": chunk_id,
                })
                
                # Gửi thông báo kết thúc chunk
                await self.websocket.send_json({
                    "type": "audio_stream_end", 
                    "chunk_id": chunk_id
                })
                
                chunk_id += 1
        except WebSocketDisconnect:
            logger.info("Client disconnected during audio sending.")
        except Exception as e:
            logger.error(f"Error in audio_sender: {e}")
        finally:
            # Gửi thông báo kết thúc luồng
            if self.websocket.client_state.name == 'CONNECTED':
                await self.websocket.send_json({"type": "stream_end"})


async def gemini_live_stream(
        audio_buffer: io.BytesIO,
        websocket: WebSocket,
        session_id = None,
        username = None,
        user_response_id = None
):
    """
    Function to handle live streaming of audio to Gemini API and send responses back via WebSocket.
    Args:
        audio_buffer (io.BytesIO): Audio data buffer to be sent to Gemini API.
        websocket (WebSocket): WebSocket connection to send responses.
        session_id (str, optional): Session identifier for tracking. Defaults to None.
        username (str, optional): Username of the user. Defaults to None.
        user_response_id (str, optional): Identifier for the user's response. Defaults to None.
    """
    try:
        # Khởi tạo phiên làm việc
        session = GeminiLiveSession(
            websocket,
            session_id=session_id,
            username=username,
            user_response_id=user_response_id
        )
        
        # Chuẩn bị phiên làm việc
        await session.setup()
        
        # Chuẩn bị audio
        try:
            processed_audio = convert_to_raw_pcm(audio_buffer)
        except Exception as e:
            logger.warning(f"Could not convert audio, using original audio: {e}")
            audio_buffer.seek(0)
            processed_audio = audio_buffer.getvalue()
            return
        
        # Gửi audio và xử lý phản hồi
        await session.send_audio(processed_audio)
        
    except Exception as e:
        logger.error(f"Error in gemini_live_stream: {e}")
        if websocket.client_state.name == 'CONNECTED':
            await websocket.send_json({
                "type": "error",
                "message": f"An error occurred: {str(e)}"
            })