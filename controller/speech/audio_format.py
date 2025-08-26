import io
import os
import subprocess
import tempfile
import numpy as np
import soundfile as sf
import logging
import wave
import tempfile
import subprocess
import os
import datetime


# Sử dụng được
def save_audio_buffer_as_wav(audio_buffer, sample_rate=16000, channels=1, sample_width=2):
    """
    Convert audio buffer to WAV file for debugging using ffmpeg for reliable conversion
    
    Args:
        audio_buffer: io.BytesIO containing audio data
        sample_rate: Target audio sample rate (default 16000Hz)
        channels: Target number of audio channels (default 1 for mono)
        sample_width: Sample width in bytes (default 2 for 16-bit)
    
    Returns:
        str: Path to the saved WAV file
    """
    # Create debug directory if it doesn't exist
    debug_dir = os.path.join(os.getcwd(), "debug_audio")
    os.makedirs(debug_dir, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(debug_dir, f"audio_debug_{timestamp}.wav")
    
    # 1. Ghi nội dung từ audio_buffer ra file tạm
    audio_buffer.seek(0)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_in:
        temp_in.write(audio_buffer.read())
        temp_input_path = temp_in.name

    # 2. Tạo file WAV chuẩn 16kHz, mono bằng ffmpeg
    temp_output_wav = tempfile.mktemp(suffix=".wav")
    command = [
        "ffmpeg", "-y", "-i", temp_input_path,
        "-acodec", "pcm_s16le", "-ar", str(sample_rate), "-ac", str(channels),
        temp_output_wav
    ]
    process = subprocess.run(command, capture_output=True)
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {process.stderr.decode()}")
    
    # 3. Copy the converted file to our debug location
    with open(temp_output_wav, 'rb') as src, open(filename, 'wb') as dst:
        dst.write(src.read())
    
    # 4. Clean up temporary files
    try:
        os.unlink(temp_input_path)
        os.unlink(temp_output_wav)
    except:
        pass
    
    print(f"Audio buffer converted and saved as WAV: {filename}")
    return filename


# Add this function to your audio_format.py file

def diagnose_audio_format(audio_bytes):
    """
    Diagnose audio format based on header bytes and other characteristics
    """
    result = {
        "size": len(audio_bytes),
        "likely_format": "unknown"
    }
    
    # Check for WAV header
    if len(audio_bytes) > 12 and audio_bytes[0:4] == b'RIFF' and audio_bytes[8:12] == b'WAVE':
        result["likely_format"] = "WAV"
        
        # Try to extract WAV format details
        try:
            import wave
            import io
            with io.BytesIO(audio_bytes) as buf:
                with wave.open(buf, 'rb') as wav:
                    result["channels"] = wav.getnchannels()
                    result["sample_width"] = wav.getsampwidth()
                    result["framerate"] = wav.getframerate()
                    result["n_frames"] = wav.getnframes()
        except Exception as e:
            result["wav_parse_error"] = str(e)
    
    # Check for OGG header
    elif len(audio_bytes) > 4 and audio_bytes[0:4] == b'OggS':
        result["likely_format"] = "OGG/Vorbis"
    
    # Check for WebM header
    elif len(audio_bytes) > 4 and audio_bytes[0:4] == b'\x1A\x45\xDF\xA3':
        result["likely_format"] = "WebM"
    
    # Likely raw PCM if none of the above and size is reasonable
    elif len(audio_bytes) % 2 == 0 and 1000 <= len(audio_bytes) <= 10000000:
        # Perform additional analysis on the first 1000 bytes to check if it looks like PCM
        sample_data = audio_bytes[:1000] if len(audio_bytes) >= 1000 else audio_bytes
        bytes_array = bytearray(sample_data)
        # Check for PCM characteristics (no bytes with value 0 in sequence, reasonable amplitude distribution)
        zero_bytes = sum(1 for byte in bytes_array if byte == 0)
        zero_ratio = zero_bytes / len(bytes_array)
        
        if zero_ratio < 0.5:  # Less than 50% zeros is typical for PCM
            result["likely_format"] = "Raw PCM"
            # Attempt to determine if it's likely 16-bit PCM
            if len(audio_bytes) % 2 == 0:
                result["possible_bit_depth"] = "16-bit"
    
    # Add the first 20 bytes for manual inspection
    if len(audio_bytes) >= 20:
        result["first_20_bytes_hex"] = audio_bytes[:20].hex()
    
    return result

def pcm_to_wav_bytes(pcm, channels=1, rate=24000, sample_width=2):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()

def convert_to_raw_pcm(audio_buffer: io.BytesIO) -> bytes:
    """
    Convert audio from various formats to raw PCM with debugging
    """
    print("[DEBUG] convert_to_raw_pcm called")
    
    # Check if buffer is at the end
    pos = audio_buffer.tell()
    print(f"[DEBUG] Buffer position at start: {pos}")
    audio_buffer.seek(0)

     # If we're at the end, go back to the beginning
    if pos == len(audio_buffer.getvalue()):
        print("[DEBUG] Buffer was at end, resetting to beginning")
        audio_buffer.seek(0)


    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        tmp.write(audio_buffer.read())
        tmp_path = tmp.name

    try:
        cmd = [
            "ffmpeg", "-y", "-i", tmp_path,
            "-f", "s16le", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-"
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode())
        return proc.stdout
    finally:
        os.remove(tmp_path)

