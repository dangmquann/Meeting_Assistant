import os
import logging
import json
import re, time
from collections import deque
from fastapi import FastAPI, Request, WebSocket
from typing import Dict, Callable, Any
from deepgram import DeepgramClient, LiveTranscriptionEvents
from dotenv import load_dotenv

load_dotenv()

dg_client = DeepgramClient(api_key=os.getenv('DEEPGRAM_API_KEY', ''))

logger = logging.getLogger("deepgram")
logger.setLevel(logging.INFO)

def format_timestamp(seconds):
    """Format seconds to HH:MM:SS.mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:06.3f}"


async def process_audio(fast_socket: WebSocket):
    async def get_transcript(event: Any) -> None:
        # Log raw JSON if available
        try:
            if hasattr(event, "to_json"):
                raw = event.to_json()
            elif hasattr(event, "to_dict"):
                raw = json.dumps(event.to_dict(), ensure_ascii=False)
            elif isinstance(event, dict):
                raw = json.dumps(event, ensure_ascii=False)
            else:
                raw = str(event)
        except Exception:
            raw = str(event)

        logger.info(f"DG RAW: {raw}")
        os.makedirs('logs', exist_ok=True)
        with open('logs/deepgram_live.jsonl', 'a', encoding='utf-8') as f:
            f.write(raw + '\n')

        # Normalize payload to extract transcript/words/is_final
        transcript = ''
        words = []
        is_final = False

        # SDK v3 typed object (LiveResultResponse)
        if hasattr(event, "channel"):
            try:
                alt0 = (event.channel.alternatives or [None])[0]
                if alt0:
                    transcript = getattr(alt0, "transcript", "") or ""
                    words = getattr(alt0, "words", []) or []
                is_final = bool(getattr(event, "is_final", False))
            except Exception:
                pass
        # Dict payload
        elif isinstance(event, dict) and 'channel' in event:
            alt = (event.get('channel', {}).get('alternatives') or [{}])[0]
            transcript = alt.get('transcript', '') or ''
            words = alt.get('words', []) or []
            is_final = bool(event.get('is_final', False))

        if transcript and is_final:
            # Majority speaker from word-level diarization
            speaker = 'unknown'
            counts = {}
            for w in words:
                # words can be dicts or typed objects
                s = w.get('speaker') if isinstance(w, dict) else getattr(w, 'speaker', None)
                if s is not None:
                    counts[s] = counts.get(s, 0) + 1
            if counts:
                speaker = max(counts, key=counts.get)

            if words:
                w0 = words[0]
                wN = words[-1]
                start_v = w0.get('start') if isinstance(w0, dict) else getattr(w0, 'start', 0)
                end_v = wN.get('end') if isinstance(wN, dict) else getattr(wN, 'end', 0)
                start_ts = format_timestamp(start_v or 0)
                end_ts = format_timestamp(end_v or 0)
            else:
                start_ts = format_timestamp(0)
                end_ts = format_timestamp(0)

            await fast_socket.send_json({
                'speaker': speaker,
                'transcript': transcript,
                'start': start_ts,
                'end': end_ts
            })

    deepgram_socket = await connect_to_deepgram(get_transcript)
    return deepgram_socket

async def connect_to_deepgram(transcript_received_handler: Callable[[Any], None]):
    try:
        # Async WebSocket client v1
        dg_ws = dg_client.listen.asyncwebsocket.v("1")

        # Handlers have signature: handler(client, ..., named args)
        async def on_transcript(_client, result=None, **kwargs):
            if result is None:
                # fallback if SDK passes differently
                result = kwargs.get("result") or kwargs
            await transcript_received_handler(result)

        async def on_close(_client, close=None, **kwargs):
            logger.info(f'Deepgram WS closed: {close}')

        async def on_error(_client, error=None, **kwargs):
            logger.error(f'Deepgram WS error: {error}')

        dg_ws.on(LiveTranscriptionEvents.Transcript, on_transcript)
        dg_ws.on(LiveTranscriptionEvents.Close, on_close)
        dg_ws.on(LiveTranscriptionEvents.Error, on_error)

        # Use dict options for websocket client
        # IMPORTANT: set encoding/sample_rate to match your input stream
        options = {
            "model": "nova-3",
            "smart_format": True,
            "punctuate": True,
            "diarize": True,
            "interim_results": True,
            "utterance_end_ms": 1000,
            "vad_events": True,
            "utterances": True,
            # Time in milliseconds of silence to wait for before finalizing speech
            "endpointing": 800,
            "language": "vi"
            # Example for raw PCM 16k mono:
            # "encoding": "linear16",
            # "sample_rate": 16000,
            # If your client sends WebM/Opus (typical from MediaRecorder):
            # "encoding": "opus",
            # "sample_rate": 48000,
        }

        await dg_ws.start(options)
        return dg_ws
    except Exception as e:
        raise Exception(f'Could not open socket: {e}')