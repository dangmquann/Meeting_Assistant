import io
import os
import subprocess
import tempfile
import numpy as np
import soundfile as sf
import logging
import wave

def pcm_to_wav_bytes(pcm, channels=1, rate=24000, sample_width=2):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()

def convert_to_raw_pcm(audio_buffer: io.BytesIO) -> bytes:
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

def convert_audio_buffer_to_raw_pcm(audio_buffer: io.BytesIO) -> bytes:
    """
    Convert an audio buffer (WebM/WAV/MP3/etc.) to raw PCM 16-bit, 16kHz mono.
    Returns the raw PCM bytes ready for Gemini Live API.
    """
    try:
        # 1. Ghi nội dung từ audio_buffer ra file tạm (WebM, WAV...)
        audio_buffer.seek(0)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_in:
            temp_in.write(audio_buffer.read())
            temp_input_path = temp_in.name

        # 2. Tạo file WAV chuẩn 16kHz, mono bằng ffmpeg
        temp_output_wav = tempfile.mktemp(suffix=".wav")
        command = [
            "ffmpeg", "-y", "-i", temp_input_path,
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            temp_output_wav
        ]
        process = subprocess.run(command, capture_output=True)
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {process.stderr.decode()}")

        # 3. Đọc WAV đã chuyển đổi
        audio, sr = sf.read(temp_output_wav)
        if audio.dtype != np.int16:
            audio = np.clip(audio, -1.0, 1.0)  # đảm bảo không vượt [-1, 1]
            audio = (audio * 32767).astype(np.int16)

        # 4. Ghi ra RAW PCM 16-bit
        buffer = io.BytesIO()
        sf.write(buffer, audio, sr, format='RAW', subtype='PCM_16')
        buffer.seek(0)
        processed_audio = buffer.read()

        return processed_audio

    finally:
        # 5. Xoá file tạm
        if os.path.exists(temp_input_path):
            os.remove(temp_input_path)
        if os.path.exists(temp_output_wav):
            os.remove(temp_output_wav)

