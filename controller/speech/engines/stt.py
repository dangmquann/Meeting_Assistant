import io
import os
import tempfile
import subprocess
import magic
import logging
from enum import Enum
from typing import Optional, Tuple
# import json_repair
from pydantic import BaseModel, Field
from openai import OpenAI
# from faster_whisper import WhisperModel
from google.cloud import speech
from google import genai
from google.genai import types
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

class TranscriptionMethod(Enum):
    GOOGLE = "google"
    OPENAI = "openai"
    GEMINI = "gemini"
    LOCAL = "local"

class WhisperModelManager:
    _instance = None
    
    @classmethod
    def get_instance(cls, model_size="medium"):
        if cls._instance is None:
            logger.info(f"Đang tải mô hình Whisper {model_size}...")
            cls._instance = WhisperModel(model_size, device="cpu", compute_type="int8")
            logger.info("Tải mô hình Whisper hoàn tất")
        return cls._instance
    
class TranscriptionResponse(BaseModel):
    transcribed_text: str
    language: str

PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

if SERVICE_ACCOUNT_FILE and os.path.exists(SERVICE_ACCOUNT_FILE):
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )


async def convert_audio_format(audio_content: bytes) -> Tuple[Optional[bytes], Optional[int], bool]:
    """
    Chuyển đổi định dạng audio sang định dạng WAV 16-bit PCM phù hợp với API nhận dạng giọng nói.
    """
    temp_input_path = None
    temp_output_path = None
    
    try:
        # Xác định loại file
        mime_type = magic.from_buffer(audio_content, mime=True)
        
        # Tạo file tạm thời cho audio đầu vào
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{mime_type.split('/')[-1]}") as temp_input:
            temp_input.write(audio_content)
            temp_input_path = temp_input.name
        
        # Tạo file tạm thời cho audio đầu ra
        temp_output_path = tempfile.mktemp(suffix=".wav")
        
        # Sử dụng ffmpeg để chuyển đổi định dạng
        command = [
            "ffmpeg", "-i", temp_input_path, 
            "-acodec", "pcm_s16le",  # 16-bit PCM
            "-ar", "16000",         # Sample rate 16kHz
            "-ac", "1",             # Mono channel
            temp_output_path
        ]
        
        process = subprocess.run(command, capture_output=True)
        
        if process.returncode != 0:
            logger.error(f"Lỗi khi chuyển đổi định dạng audio: {process.stderr.decode()}")
            return None, None, False
        
        # Đọc file đã chuyển đổi
        with open(temp_output_path, "rb") as f:
            converted_audio = f.read()
        
        return converted_audio, 16000, True
    
    except Exception as e:
        logger.error(f"Lỗi khi chuyển đổi định dạng audio: {str(e)}")
        return None, None, False
    
    finally:
        # Dọn dẹp các file tạm thời
        if temp_input_path and os.path.exists(temp_input_path):
            try:
                os.unlink(temp_input_path)
            except Exception:
                pass
                
        if temp_output_path and os.path.exists(temp_output_path):
            try:
                os.unlink(temp_output_path)
            except Exception:
                pass

async def transcribe_with_google(audio_content: bytes) -> str:
    """
    Chuyển đổi âm thanh thành văn bản sử dụng Google Speech-to-Text API với tự động phát hiện ngôn ngữ.
    """
    try:
        
        #Chuyển đổi định dạng audio nếu cần
        converted_audio, sample_rate, success = await convert_audio_format(audio_content)
        
        if not success:
            return None
        
        # Khởi tạo client Google Speech-to-Text
        client = speech.SpeechClient()

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "caimio")
        if not project_id:
            logger.error("GOOGLE_CLOUD_PROJECT không được cấu hình")
            return None
        
        language_codes = [
            "en-US",  # English (US)
            "vi-VN",  # Vietnamese
            "ja-JP",  # Japanese
            "ko-KR",  # Korean
            "zh-CN"   # Chinese (Simplified)
        ]
        config = cloud_speech.RecognitionConfig(
            auto_decoding_config = cloud_speech.AutoDetectDecodingConfig(),
            language_codes = language_codes,
            model = "latest_long",
        )

        request = cloud_speech.RecognizeRequest(
            recognizer=f"projects/{project_id}/locations/global/recognizers/_",
            config=config,
            content=converted_audio,
        )
        response = client.recognize(request=request)

        # Xử lí kết quả
        transcribed_text = ""
        for result in response.results:
            transcribed_text += result.alternatives[0].transcript
            # if hasattr(result, 'language_code'):
            #     logger.info(f"Phát hiện ngôn ngữ: {result.language_code}")
        return transcribed_text.strip()
        
    except Exception as e:
        logger.error(f"Lỗi khi chuyển đổi audio với Google API: {str(e)}")
        return None

async def transcribe_with_openai(audio_content: bytes) -> str:
    """
    Chuyển đổi âm thanh thành văn bản sử dụng OpenAI Whisper API với tự động phát hiện ngôn ngữ.
    """
    temp_path = None
    try:
        # Lưu audio thành file tạm thời
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(audio_content)
            temp_path = temp_file.name
        
        # Khởi tạo OpenAI client
        client = OpenAI()
        
        # Gửi file âm thanh tới API - không chỉ định language để tự động phát hiện
        with open(temp_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-1", # whisper-1, gpt-4o-transcribe
                file=audio_file,
            )

        # Trả về kết quả
        return response.text
        
    except Exception as e:
        logger.error(f"Lỗi khi chuyển đổi audio bằng OpenAI Whisper: {str(e)}")
        return None
    
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass

async def transcribe_with_genai(audio_content: bytes) -> str:
    contents = []

    try:
        contents.append(types.Part.from_bytes(
            data=audio_content,
            mime_type="audio/wav"  
        ))

        contents.append(types.Part.from_text(text="""Transcribe the audio to text, ensure your response is correct, fully and the same language as the audio. Format your response as a JSON object with the following fields: {"transcribed_text": "the transcribed text", "language": "the language of the transcribed text"}""")) 

        client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION, credentials=credentials)

        response = await client.aio.models.generate_content(
            model='gemini-2.0-flash',
            contents=contents,
            config={
                "response_mime_type": "application/json",
                "response_schema": TranscriptionResponse,
            },  
        )
        logger.info(f"Response from GenAI: {response}")
        if not response or not response.text:
            logger.error("Không nhận được phản hồi từ GenAI")
            return None

        response_dict = json_repair.loads(response.text)
        logger.info(f"Response JSON: {response_dict}")
        transcribed_text = response_dict.get("transcribed_text")
        logger.info(f"Transcribed text: {transcribed_text}")
        language = response_dict.get("language")
        logger.info(f"Detected language: {language}")

        return transcribed_text.strip()

    except Exception as e:
        logger.error(f"Failed to transcribe audio with GenAI: {str(e)}")
        return None
    


async def transcribe_with_local(audio_content: bytes) -> str:
    """
    Chuyển đổi âm thanh thành văn bản sử dụng mô hình Whisper local với tự động phát hiện ngôn ngữ.
    """
    temp_path = None
    try:
        # Lưu audio thành file tạm thời
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(audio_content)
            temp_path = temp_file.name
        
        # Lấy instance mô hình Whisper
        model = WhisperModelManager.get_instance(model_size="medium")  # medium có độ chính xác tốt hơn
        
        # Thực hiện chuyển đổi với tự động phát hiện ngôn ngữ
        segments, info = model.transcribe(temp_path)
        
        # Xử lý kết quả
        result = " ".join([segment.text for segment in segments])
        
        # Ghi log ngôn ngữ phát hiện được
        if info.language:
            logger.info(f"Phát hiện ngôn ngữ: {info.language} (độ tin cậy: {info.language_probability:.2f})")
        
        return result.strip()
        
    except Exception as e:
        logger.error(f"Lỗi khi chuyển đổi audio bằng local Whisper: {str(e)}")
        return None
    
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass

async def speech2text(
    audio_content: bytes, 
    method: str = "openai", 
    fallback: bool = True,
    **kwargs
) -> Optional[str]:
    """
    Chuyển đổi âm thanh thành văn bản với nhiều phương pháp khác nhau.
    
    Args:
        audio_content: Dữ liệu audio dưới dạng bytes
        method: Phương pháp chuyển đổi ('google', 'openai', 'local')
        fallback: Có sử dụng phương pháp dự phòng nếu phương pháp chính thất bại
        
    Returns:
        Văn bản được chuyển đổi từ audio
    """
    # Kiểm tra kích thước audio
    if len(audio_content) > 25 * 1024 * 1024:  # 25MB
        logger.warning("Audio quá lớn, vượt quá 25MB")
        return None
    
    # Chuyển đổi string method thành TranscriptionMethod enum
    method_lower = method.lower()
    if method_lower == "google":
        transcription_method = TranscriptionMethod.GOOGLE
    elif method_lower == "openai":
        transcription_method = TranscriptionMethod.OPENAI
    elif method_lower == "local":
        transcription_method = TranscriptionMethod.LOCAL
    elif method_lower == "gemini":
        transcription_method = TranscriptionMethod.GEMINI
    else:
        logger.warning(f"Phương pháp không hợp lệ: {method}, sử dụng Google Speech-to-Text")
        transcription_method = TranscriptionMethod.GOOGLE
    
    try:
        # Xử lý theo phương pháp được chọn

        
        if transcription_method == TranscriptionMethod.OPENAI:
            result = await transcribe_with_openai(audio_content)
            model_id = "whisper-1"
            if result is None and fallback:
                logger.info("OpenAI Whisper thất bại, chuyển sang Gemini")
                result = await transcribe_with_genai(audio_content)
                if result is None:
                    logger.info("Whisper local thất bại, chuyển sang Google Speech-to-Text")
                    result = await transcribe_with_google(audio_content)
        elif transcription_method == TranscriptionMethod.GEMINI:
            result = await transcribe_with_genai(audio_content)
            model_id = "gemini/gemini-2.0-flash"
            if result is None and fallback:
                logger.info("Gemini thất bại, chuyển sang OpenAI Whisper")
                result = await transcribe_with_openai(audio_content)

        elif transcription_method == TranscriptionMethod.GOOGLE:
            result = await transcribe_with_google(audio_content)
            model_id = "google-speech-to-text"
            if result is None and fallback:
                logger.info("Google Speech-to-Text thất bại, chuyển sang Whisper local")
                result = await transcribe_with_local(audio_content)
                if result is None:
                    logger.info("Whisper local thất bại, chuyển sang OpenAI Whisper")
                    result = await transcribe_with_openai(audio_content)
        
        elif transcription_method == TranscriptionMethod.LOCAL:
            result = await transcribe_with_local(audio_content)
            model_id = "faster-whisper"
            if result is None and fallback:
                logger.info("Whisper local thất bại, chuyển sang Google Speech-to-Text")
                result = await transcribe_with_google(audio_content)
                if result is None:
                    logger.info("Google Speech-to-Text thất bại, chuyển sang OpenAI Whisper")
                    result = await transcribe_with_openai(audio_content)
        else:
            logger.error(f"Phương pháp không được hỗ trợ: {transcription_method}")
            return None
            
        return result, model_id
    
    except Exception as e:
        logger.error(f"Lỗi khi chuyển đổi audio sang text: {str(e)}")
        return None
