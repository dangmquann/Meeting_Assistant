import asyncio 
import io
import base64
import logging
import datetime
import uuid
import os
import soundfile as sf
import librosa
from google import genai 
from google.genai import types
from fastapi import WebSocket, WebSocketDisconnect

from modules.speech.audio_format import convert_to_raw_pcm

logger = logging.getLogger("live_gemini")

class GeminiLiveSession:
    def __init__(
        self, 
        websocket, 
        model="gemini-2.5-flash-preview-native-audio-dialog", 
        # model="gemini-live-2.5-flash-preview", 
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
            "input_audio_transcription": {},
            "output_audio_transcription": {},
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
            print("Starting Gemini Live API connection")
            async with self.client.aio.live.connect(model=self.model, config=self.config) as session:
                # Gửi audio tới Gemini
                await session.send_realtime_input(
                    audio=types.Blob(data=processed_audio, mime_type="audio/pcm;rate=16000")
                )
                await session.send_realtime_input(audio_stream_end=True)
                print("Audio sent to Gemini Live API")

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
                # Process audio data
                if response.data:
                    print("Received audio data from Gemini")
                    await self.gemini_response_queue.put(response.data)
                
                # Process server content if available
                if response.server_content:
                    # Handle input transcription
                    print("Processing server content from Gemini")
                    if hasattr(response.server_content, 'input_transcription') and response.server_content.input_transcription:
                        input_text = response.server_content.input_transcription.text
                        print(f"Input transcript: {input_text}")
                        # Send transcript to client
                        await self.websocket.send_json({
                            "type": "input_transcript",
                            "text": input_text
                        })
                    
                    # Handle output transcription
                    if hasattr(response.server_content, 'output_transcription') and response.server_content.output_transcription:
                        output_text = response.server_content.output_transcription.text
                        print(f"Output transcript: {output_text}")
                        # Send transcript to client
                        await self.websocket.send_json({
                            "type": "output_transcript", 
                            "text": output_text
                        })
                    
                    # Log model turn if available
                    if hasattr(response.server_content, 'model_turn') and response.server_content.model_turn is not None:
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
                
                # Mã hóa và gửi audio chunk
                audio_b64 = base64.b64encode(audio_data).decode()
                await self.websocket.send_json({
                    "type": "audio_chunk",
                    "chunk": audio_b64,
                    "chunk_id": chunk_id,
                    "encoding": "pcm_s16le",
                    "sample_rate": 24000, #sample rate from gemini
                    "channels": 1
                })

                print(f"Sent audio chunk {chunk_id} of length {len(audio_data)} bytes")
                
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
        audio_buffer.seek(0)
        
        # Chuẩn bị audio
        try:
            processed_audio = convert_to_raw_pcm(audio_buffer)
            print(f"[DEBUG] PCM conversion successful. Processed audio length: {len(processed_audio)} bytes")
            
            # Save processed audio for comparison
            with open("temp_processed_audio.pcm", "wb") as f:
                f.write(processed_audio)
            print("[DEBUG] Saved processed audio to temp_processed_audio.pcm")

        except Exception as e:
            logger.warning(f"Could not convert audio, using original audio: {e}")
            # processed_audio = original_audio
        print(f"[DEBUG] Final audio to be sent to Gemini: {len(processed_audio)} bytes")

        # Gửi audio và xử lý phản hồi
        await session.send_audio(processed_audio)
       
        
    except Exception as e:
        logger.error(f"Error in gemini_live_stream: {e}")
        if websocket.client_state.name == 'CONNECTED':
            await websocket.send_json({
                "type": "error",
                "message": f"An error occurred: {str(e)}"
            })