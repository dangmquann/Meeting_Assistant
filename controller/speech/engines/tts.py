import io
import os
import tempfile
import subprocess
import magic
import logging
from enum import Enum
from typing import Optional, Tuple
from openai import OpenAI
from openai import AsyncOpenAI
from faster_whisper import WhisperModel
from google.cloud import speech
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
from google import genai
from google.genai import types
from V2_chat.controller.speech.audio_format import pcm_to_wav_bytes

logger = logging.getLogger(__name__)

class TTSModel(Enum):
    OPENAI = "openai"
    GOOGLE = "google"
    GEMINI = "gemini"

class VoiceOption(Enum):
    #OpenAI voices
    ALLOY = "alloy"
    ECHO = "echo"
    FABLE = "fable"
    ONYX = "onyx"
    NOVA = "nova"
    SHIMMER = "shimmer"
    
    # Gemini voices
    GEMINI_MALE = "male"
    GEMINI_FEMALE = "female"



async def text2speech(
        text: str,
        model: str = "gpt-4o-mini-tts",
        voice: str = "alloy",
        format: str = "mp3",
        speed: float = 1.0,
        fallback: bool = True
) -> Optional[bytes]:
    """ 
    Convert text to speech using OpenAI or Google TTS.
    Args:
        text: The text to convert to speech.
        model: The TTS model to use (OpenAI, Google, etc.).
        voice: The voice option to use.
        format: The audio format to return (mp3, wav).
        speed: The speed of the speech.
        fallback: Whether to use a fallback method if the primary fails.
    Returns:
        The audio content as bytes, or None if conversion fails.
    """
    try:
        # Check length of text
        if len(text) == 0:
            logger.warning("Text is empty, returning None")
            return None
        
        if "gpt-4o" in model:
            tts_model = TTSModel.OPENAI
        elif "gemini" in model:
            tts_model = TTSModel.GEMINI
        else:
            logger.warning(f"Unsupported TTS model: {model}, using OpenAI as default")
            tts_model = TTSModel.OPENAI
            model = "gpt-4o-mini-tts"
        
        # Handle OpenAI TTS
        if tts_model == TTSModel.OPENAI:
            result = await _openai_tts(
                text=text,
                model=model,
                voice=voice,
                format=format,
                speed=speed
            )
        else:
            result = await _gemini_tts(
                text=text,
                model=model,
                voice=voice,
                speed=speed
            )
        
        #Handle fallback
        if result is None and fallback:
            logger.info("Primary TTS method failed, trying fallback")
            if tts_model == TTSModel.OPENAI:
                result = await _gemini_tts(
                    text=text,
                    model=model,
                    voice=voice,
                    speed=speed
                )
            else:
                result = await _openai_tts(
                    text=text,
                    model=model,
                    voice=voice,
                    format=format,
                    speed=speed
                )
        return result
    except Exception as e:
        logger.error(f"Error in text2speech: {str(e)}")
        return None
    
async def _openai_tts(
        text: str,
        model: str = "gpt-4o-mini-tts",
        voice: str = "alloy",
        format: str = "mp3",
        speed: float = 1.0,
        instructions: str = None
) -> Optional[bytes]:
    """
    Convert text to speech using OpenAI TTS with streaming response.
    
    Args:
        text: The text to convert to speech.
        model: The TTS model to use (e.g., "gpt-4o-mini-tts", "tts-1").
        voice: The voice option to use (alloy, echo, fable, onyx, nova, shimmer, coral).
        format: The audio format to return (mp3, opus, aac, flac).
        speed: The speed of the speech (0.25 to 4.0).
        instructions: Optional speaking style instructions.
        
    Returns:
        The audio content as bytes, or None if conversion fails.
    """
    try:
        import io
        from openai import OpenAI
        
        max_length = 4096
        if len(text) > max_length:
            logger.warning(f"Text length {len(text)} exceeds OpenAI TTS limit of {max_length}, truncating")
            text = text[:max_length]
        
        valid_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer", "coral"]
        if voice not in valid_voices:
            logger.warning(f"Invalid voice '{voice}', defaulting to 'alloy'")
            voice = "alloy"
        
        if speed < 0.25 or speed > 4.0:
            logger.warning(f"Invalid speed {speed}, clamping to valid range")
            speed = max(0.25, min(4.0, speed))

        # Initialize OpenAI client
        client = AsyncOpenAI()
        
        # Create request parameters
        request_params = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": format,
            "speed": speed,
            "instructions": "Speak like a Master of Ceremonies with a cheerful and positive tone.",
            "response_format": "wav",
        }
        
        # Add instructions if provided
        if instructions:
            request_params["instructions"] = instructions

        res_content = await client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice="fable",
                input=text,
                speed=1.0,
                instructions="Speak like a Master of Ceremonies with a cheerful and positive tone.",
                response_format="wav",
            )
        audio_data = res_content.content
        if audio_data:
            return audio_data
        else:
            logger.error("No audio data returned from OpenAI TTS")
            return None
    
    except Exception as e:
        logger.error(f"Error in OpenAI TTS: {str(e)}")
        return None
    
async def _gemini_tts(
        text: str,
        model: str = "gemini-2.5-flash-preview-tts",
        voice: str = "Kore",
        speed: float = 1.0,
        format: str = "mp3"  # Not directly used by Gemini but kept for API consistency
) -> Optional[bytes]:
    """
    Convert text to speech using Google Gemini TTS.
    
    Args:
        text: The text to convert to speech
        model: The TTS model name (should be "gemini-2.5-flash-preview")
        voice: Voice name to use (see list of 30 available voices below)
        speed: Speech speed multiplier (0.25 to 4.0)
        format: Format parameter (maintained for API consistency)
        
    Available voices:
        - Zephyr (Bright)      - Puck (Upbeat)        - Charon (Informative)
        - Kore (Firm)          - Fenrir (Excitable)   - Leda (Youthful)
        - Orus (Firm)          - Aoede (Breezy)       - Callirrhoe (Easy-going)
        - Autonoe (Bright)     - Enceladus (Breathy)  - Iapetus (Clear)
        - Umbriel (Easy-going) - Algieba (Smooth)     - Despina (Smooth)
        - Erinome (Clear)      - Algenib (Gravelly)   - Rasalgethi (Informative)
        - Laomedeia (Upbeat)   - Achernar (Soft)      - Alnilam (Firm)
        - Schedar (Even)       - Gacrux (Mature)      - Pulcherrima (Forward)
        - Achird (Friendly)    - Zubenelgenubi (Casual) - Vindemiatrix (Gentle)
        - Sadachbia (Lively)   - Sadaltager (Knowledgeable) - Sulafat (Warm)
        
    Returns:
        Audio content as bytes, or None if conversion fails
    """
    try:
        from google import genai
        from google.genai import types
        import base64
        
        client = genai.Client()
        logger.info(f"Using Gemini TTS model: {model}, voice: {voice}, speed: {speed}")
        
        # Map legacy voice inputs to specific Gemini voices
        voice_mapping = {
            "male": "Kore",     # Default male voice (Firm)
            "female": "Aoede",  # Default female voice (Breezy)
            "tenor": "Orus",    # Alternative male voice
            "soprano": "Leda",  # Alternative female voice
            
            # Keep all actual voice names as-is for direct access
            "zephyr": "Zephyr", "puck": "Puck", "charon": "Charon",
            "kore": "Kore", "fenrir": "Fenrir", "leda": "Leda",
            "orus": "Orus", "aoede": "Aoede", "callirrhoe": "Callirrhoe",
            "autonoe": "Autonoe", "enceladus": "Enceladus", "iapetus": "Iapetus",
            "umbriel": "Umbriel", "algieba": "Algieba", "despina": "Despina",
            "erinome": "Erinome", "algenib": "Algenib", "rasalgethi": "Rasalgethi",
            "laomedeia": "Laomedeia", "achernar": "Achernar", "alnilam": "Alnilam",
            "schedar": "Schedar", "gacrux": "Gacrux", "pulcherrima": "Pulcherrima",
            "achird": "Achird", "zubenelgenubi": "Zubenelgenubi", "vindemiatrix": "Vindemiatrix",
            "sadachbia": "Sadachbia", "sadaltager": "Sadaltager", "sulafat": "Sulafat"
        }
        
        # Get voice name, with fallback to Kore if not found
        gemini_voice = voice
        if voice.lower() in voice_mapping:
            gemini_voice = voice_mapping[voice.lower()]
        
        # Check if voice name is valid (case-sensitive)
        valid_voices = [
            "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", 
            "Orus", "Aoede", "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", 
            "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi", 
            "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima", 
            "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat"
        ]
        
        if gemini_voice not in valid_voices:
            logger.warning(f"Invalid Gemini voice '{gemini_voice}', using default 'Kore'")
            gemini_voice = "Kore"
        
        # Ensure text has proper punctuation for better TTS quality
        if text and not text.strip().endswith(('.', '!', '?', ':', ';')):
            text = text.strip() + "."
        
        # Create the generate content request
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=gemini_voice,
                        )
                    ),
                ),
            )
        )
        
        # Extract audio data
        if (response and response.candidates and 
            len(response.candidates) > 0 and 
            response.candidates[0].content and 
            response.candidates[0].content.parts and 
            len(response.candidates[0].content.parts) > 0):
            
            audio_data = response.candidates[0].content.parts[0].inline_data.data
            audio_data = pcm_to_wav_bytes(audio_data)  # Convert PCM to WAV bytes
            logger.info(f"Received audio data of length {len(audio_data)} bytes")
            logger.info(f"Gemini TTS mime_type: {response.candidates[0].content.parts[0].inline_data.mime_type}")
            # if isinstance(audio_data, str):
            #     # If returned as base64 string, decode it
            #     audio_data = base64.b64decode(audio_data)
            return audio_data
        else:
            logger.error("No audio data returned from Gemini TTS")
            return None
            
    except Exception as e:
        logger.error(f"Error in Gemini TTS: {str(e)}")
        return None
    
