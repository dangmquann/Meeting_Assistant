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
from google.oauth2 import service_account
from google.genai.types import (
    AudioTranscriptionConfig,
    AutomaticActivityDetection,
    Content,
    EndSensitivity,
    GoogleSearch,
    LiveConnectConfig,
    Part,
    PrebuiltVoiceConfig,
    ProactivityConfig,
    RealtimeInputConfig,
    SpeechConfig,
    StartSensitivity,
    Tool,
    ToolCodeExecution,
    VoiceConfig,
    HttpOptions
)
from pathlib import Path
from controller.speech.audio_format import convert_to_raw_pcm
# from dotenv import load_dotenv
# load_dotenv()

logger = logging.getLogger("live_gemini")

# PROJECT_ID = os.getenv("PROJECT_ID")
# LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")
# SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
# credentials = service_account.Credentials.from_service_account_file(
#     SERVICE_ACCOUNT_FILE,
#     scopes=['https://www.googleapis.com/auth/cloud-platform']
# )

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
        # vertexai=True, credentials=credentials,
        #                             project=PROJECT_ID, location=LOCATION,

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
                    "silence_duration_ms": 800,
                }
            }
        }
        self.conversation_history = []  # Lưu trữ lịch sử cuộc trò chuyện
    
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
                # audio_bytes = Path("/home/quandm/quandm/meeting_assistant/sample.pcm").read_bytes()

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

                        # Tích lũy văn bản từ người dùng
                        if input_text.strip():
                            # Kiểm tra nếu message cuối cùng cũng từ user thì nối vào, nếu không thì tạo mới
                            if (hasattr(self, 'conversation_history') and 
                                self.conversation_history and 
                                self.conversation_history[-1]["role"] == "user"):
                                self.conversation_history[-1]["content"] += input_text
                                self.conversation_history[-1]["timestamp"] = datetime.datetime.now().isoformat()
                            else:
                                if not hasattr(self, 'conversation_history'):
                                    self.conversation_history = []
                                self.conversation_history.append({
                                    "role": "user",
                                    "content": input_text,
                                    "timestamp": datetime.datetime.now().isoformat()
                                })
                        else:
                            pass

                        # Send transcript to client
                        await self.websocket.send_json({
                            "role": "user",
                            "type": "input_transcript",
                            "text": input_text,
                            "timestamp": datetime.datetime.now().isoformat()
                        })
                    
                    # Handle output transcription
                    if hasattr(response.server_content, 'output_transcription') and response.server_content.output_transcription:
                        output_text = response.server_content.output_transcription.text
                        print(f"Output transcript: {output_text}")

                        
                        # Tích lũy văn bản từ assistant
                        if output_text.strip():
                            # Kiểm tra nếu message cuối cùng cũng từ assistant thì nối vào, nếu không thì tạo mới
                            if (hasattr(self, 'conversation_history') and 
                                self.conversation_history and 
                                self.conversation_history[-1]["role"] == "assistant"):
                                self.conversation_history[-1]["content"] += output_text
                                self.conversation_history[-1]["timestamp"] = datetime.datetime.now().isoformat()
                            else:
                                if not hasattr(self, 'conversation_history'):
                                    self.conversation_history = []
                                self.conversation_history.append({
                                    "role": "assistant",
                                    "content": output_text,
                                    "timestamp": datetime.datetime.now().isoformat()
                                })
                        else:
                            pass

                        # Send transcript to client
                        await self.websocket.send_json({
                            "role": "assistant",
                            "type": "output_transcript", 
                            "text": output_text,
                            "timestamp": datetime.datetime.now().isoformat()
                        })
                    
                    # Log model turn if available
                    if hasattr(response.server_content, 'model_turn') and response.server_content.model_turn is not None:
                        if hasattr(self, "_idle_task") and self._idle_task and not self._idle_task.done():
                            self._idle_task.cancel()
                        await self.websocket.send_json({"type": "audio_stream_end"})
        except Exception as e:
            logger.error(f"Error receiving from Gemini: {e}")
        finally:
            # Báo hiệu kết thúc luồng
            await self.gemini_response_queue.put(None)
            # Lưu nội dung cuộc hội thoại khi kết thúc phiên
            # await self.save_conversation()
    
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
                
                # # Gửi thông báo kết thúc chunk
                # await self.websocket.send_json({
                #     "type": "audio_stream_end", 
                #     "chunk_id": chunk_id
                # })
                
                chunk_id += 1
        except WebSocketDisconnect:
            logger.info("Client disconnected during audio sending.")
        except Exception as e:
            logger.error(f"Error in audio_sender: {e}")
        finally:
            # Gửi thông báo kết thúc luồng
            if self.websocket.client_state.name == 'CONNECTED':
                await self.websocket.send_json({"type": "stream_end"})
    
    async def save_conversation(self):
        """Tự động lưu nội dung cuộc hội thoại vào file."""
        try:
            print("Saving conversation history...")
            # Kiểm tra nếu không có nội dung để lưu
            if not hasattr(self, 'conversation_history') or not self.conversation_history:
                logger.info("No conversation content to save")
                return
            
            # Tạo thư mục lưu trữ nếu chưa tồn tại
            save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                                    "conversations")
            os.makedirs(save_dir, exist_ok=True)
            
            # Tạo tên file với timestamp để tránh trùng lặp
            now = datetime.datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            session_id = self.session_id or "unknown_session"
            filename = f"meeting_{session_id}_{timestamp}.txt"
            filepath = os.path.join(save_dir, filename)
            
            # Ghi nội dung vào file
            with open(filepath, "w", encoding="utf-8") as f:
                for msg in self.conversation_history:
                    speaker = "Người dùng" if msg["role"] == "user" else "Caimio"
                    msg_time = datetime.datetime.fromisoformat(msg["timestamp"]).strftime("%H:%M:%S")
                    f.write(f"[{msg_time}] {speaker}:\n{msg['content']}\n\n")
            
            logger.info(f"Đã tự động lưu nội dung cuộc hội thoại vào {filepath}")
            
            # Thông báo cho client rằng đã lưu nội dung
            if self.websocket.client_state.name == 'CONNECTED':
                await self.websocket.send_json({
                    "type": "conversation_saved",
                    "filename": filename,
                    "message": f"Đã tự động lưu nội dung cuộc hội thoại"
                })
            
            return filepath
            
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            if self.websocket.client_state.name == 'CONNECTED':
                await self.websocket.send_json({
                    "type": "error",
                    "message": f"Không thể lưu nội dung cuộc hội thoại: {str(e)}"
                })
            return None


    async def setup_continuous_stream(self):
        """Set up a persistent streaming session for continuous audio"""
        logger.debug("Setting up continuous Gemini Live streaming session")
        await self.websocket.send_json({
            "type": "processing",
            "message": "Setting up continuous streaming session..."
        })
        
        self.stream_active = True
        self.streaming_session = None
        self.audio_buffer = []  # Buffer to accumulate audio chunks
    

    async def _safe_close_session(self, timeout: float = 1.0):
        import contextlib, asyncio, logging
        # Hủy các task phụ trợ
        if getattr(self, "_idle_task", None) and not self._idle_task.done():
            self._idle_task.cancel()
        for t in (getattr(self, 'receiver_task', None), getattr(self, 'sender_task', None)):
            if t and not t.done():
                t.cancel()
        # Gửi end nhẹ nhàng (không bắt buộc)
        if getattr(self, "streaming_session", None):
            with contextlib.suppress(Exception):
                await self.streaming_session.send_realtime_input(audio_stream_end=True)
        # Đóng context __aexit__ có timeout
        if getattr(self, "_cm", None):
            try:
                await asyncio.wait_for(self._cm.__aexit__(None, None, None), timeout=timeout)
            except asyncio.TimeoutError:
                logging.getLogger("live_gemini").warning("Timeout while closing Gemini session; drop it.")
        # Reset state
        self.streaming_session = None
        self._cm = None

    
    async def start_streaming_session(self):
        # Đóng phiên cũ CHUẨN trước khi tạo phiên mới
        if self.streaming_session is not None:
            await self._safe_close_session()

        # Mở phiên mới
        self._cm = self.client.aio.live.connect(model=self.model, config=self.config)
        self.streaming_session = await self._cm.__aenter__()

        # Bật 2 task nền
        self.receiver_task = asyncio.create_task(self._receive_responses(self.streaming_session))
        self.sender_task   = asyncio.create_task(self._send_audio_chunks())
        return self.streaming_session
    
    def _arm_idle_timer(self, timeout=1.2):
        if getattr(self, "_idle_task", None) and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = asyncio.create_task(self._idle_flush_after(timeout))

    async def _idle_flush_after(self, t):
        try:
            await asyncio.sleep(t)
            if getattr(self, "streaming_session", None):
                # ĐỪNG để exception văng ra khi socket đã đóng
                import contextlib
                with contextlib.suppress(Exception):
                    await self.streaming_session.send_realtime_input(audio_stream_end=True)
        except asyncio.CancelledError:
            pass


    async def process_audio_chunk(self, audio_chunk):
        """Process a single audio chunk in the continuous stream"""
        print(f"chunk_in len={len(audio_chunk)}, session_open={self.streaming_session is not None}")

        if not self.stream_active:
            return
            
        if self.streaming_session is None:
            await self.start_streaming_session()
            
        try:
            # Send the audio chunk to Gemini
            await self.streaming_session.send_realtime_input(
                audio=types.Blob(data=audio_chunk, mime_type="audio/pcm;rate=16000")
            )

            self._arm_idle_timer(timeout=1.2)
            
        except Exception as e:
            logger.error(f"Error sending audio chunk: {e}")
            # Try to restart session on error
            # await self.start_streaming_session()
            await self._safe_close_session()
    
    async def pause_streaming(self):
        self.stream_active = False
        if hasattr(self, "_idle_task") and self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        if getattr(self, "streaming_session", None):
            try:
                await self.streaming_session.send_realtime_input(audio_stream_end=True)
            except Exception:
                pass

    
    async def resume_streaming(self):
        """Resume the continuous audio stream"""
        self.stream_active = True
    
    # End session (đóng context)
    async def end_streaming(self):
        if hasattr(self, "_idle_task") and self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        if self.streaming_session:
            try:
                try:
                    await self.streaming_session.send_realtime_input(audio_stream_end=True)
                except:
                    pass
                if hasattr(self, 'receiver_task') and not self.receiver_task.done():
                    self.receiver_task.cancel()
                if hasattr(self, 'sender_task') and not self.sender_task.done():
                    self.sender_task.cancel()
            finally:
                if hasattr(self, '_cm'):
                    await self._cm.__aexit__(None, None, None)
                self.streaming_session = None
                self._cm = None

async def gemini_live_stream(
        audio_buffer: io.BytesIO,
        websocket: WebSocket,
        session_id = None,
        username = None,
        user_response_id = None,
        end_session = False
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
        # Khởi tạo session_id nếu chưa có
        if not session_id:
            session_id = str(uuid.uuid4())

        # Khởi tạo phiên làm việc
        session = GeminiLiveSession(
            websocket,
            session_id=session_id,
            username=username,
            user_response_id=user_response_id
        )

        if not hasattr(session, 'conversation_history'):
            session.conversation_history = []
        
        # Chuẩn bị phiên làm việc
        await session.setup()
        audio_buffer.seek(0)
        
        # Chuẩn bị audio
        try:
            processed_audio = convert_to_raw_pcm(audio_buffer)
            print(f"[DEBUG] PCM conversion successful. Processed audio length: {len(processed_audio)} bytes")
            
        except Exception as e:
            logger.warning(f"Could not convert audio, using original audio: {e}")
            processed_audio = audio_buffer.getvalue()
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