import asyncio
import json
import logging
import os
from contextlib import suppress
from typing import Any, Callable

from fastapi import WebSocket
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.extensions.types.sockets import ListenV1ControlMessage, ListenV1ResultsEvent
from dotenv import load_dotenv
# from controller.history_database import insert_response, responseModel

load_dotenv()

dg_client = AsyncDeepgramClient(api_key=os.getenv('DEEPGRAM_API_KEY', ''))

logger = logging.getLogger("meeting_assistant")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


class DeepgramSocketWrapper:
    def __init__(self, *, context_manager, socket, listener_task: asyncio.Task):
        self._context_manager = context_manager
        self._socket = socket
        self._listener_task = listener_task
        self._closed = False
        self._transcript = ""
        listener_task.add_done_callback(self._on_listener_done)

    @staticmethod
    def _on_listener_done(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error("Deepgram listener exited with error: %s", exc)

    async def send(self, data: bytes) -> None:
        if self._closed:
            return
        await self._socket.send_media(data)

    async def finalize(self) -> None:
        if self._closed:
            return
        try:
            await self._socket.send_control(ListenV1ControlMessage(type="Finalize"))
        except Exception as error:
            logger.debug("Deepgram finalize failed: %s", error)

    async def finish(self) -> None:
        await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            try:
                await self._context_manager.__aexit__(None, None, None)
            except Exception as error:
                logger.debug("Deepgram socket close error: %s", error)
        finally:
            if self._listener_task:
                try:
                    await asyncio.wait_for(self._listener_task, timeout=1)
                except asyncio.TimeoutError:
                    self._listener_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await self._listener_task
                except asyncio.CancelledError:
                    pass


def format_timestamp(seconds):
    """Format seconds to HH:MM:SS.mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:06.3f}"


async def process_audio(fast_socket: WebSocket):
    async def get_transcript(event: Any) -> None:
        try:
            if isinstance(event, ListenV1ResultsEvent):
                raw = event.json()
            elif hasattr(event, "to_json"):
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
        speech_final = False
        start_seconds = None
        end_seconds = None
        channel_index = None
        confidence = None

        if isinstance(event, ListenV1ResultsEvent):
            channel_index = (event.channel_index or [None])[0]
            alt0 = event.channel.alternatives[0] if event.channel.alternatives else None
            if alt0:
                transcript = getattr(alt0, "transcript", "") or ""
                words = list(getattr(alt0, "words", []) or [])
                confidence = getattr(alt0, "confidence", None)
            is_final = bool(getattr(event, "is_final", False) or getattr(event, "speech_final", False))
            start_seconds = getattr(event, "start", None)
            duration = getattr(event, "duration", None)
            if start_seconds is not None and duration is not None:
                end_seconds = start_seconds + duration
        elif hasattr(event, "channel"):
            try:
                alt0 = (event.channel.alternatives or [None])[0]
                if alt0:
                    transcript = getattr(alt0, "transcript", "") or ""
                    words = getattr(alt0, "words", []) or []
                    confidence = getattr(alt0, "confidence", None)
                is_final = bool(getattr(event, "is_final", False))
            except Exception:
                pass
        elif isinstance(event, dict) and 'channel' in event:
            alt = (event.get('channel', {}).get('alternatives') or [{}])[0]
            transcript = alt.get('transcript', '') or ''
            words = alt.get('words', []) or []
            is_final = event.get('is_final', False)
            speech_final = event.get('speech_final', False)
            channel_index = (event.get('channel_index') or [None])[0]
            start_seconds = event.get('start')
            duration = event.get('duration')
            if start_seconds is not None and duration is not None:
                end_seconds = start_seconds + duration

        if not transcript:
            return

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
            start_v = w0.get('start') if isinstance(w0, dict) else getattr(w0, 'start', None)
            end_v = wN.get('end') if isinstance(wN, dict) else getattr(wN, 'end', None)
            if start_v is not None:
                start_seconds = start_v
            if end_v is not None:
                end_seconds = end_v

        if start_seconds is None:
            start_seconds = 0.0
        if end_seconds is None:
            end_seconds = start_seconds

        start_ts = format_timestamp(start_seconds)
        end_ts = format_timestamp(end_seconds)
        result_id = f"{channel_index or 0}-{int(start_seconds * 1000)}"

        # Tích lũy transcript khi is_final = True
        if is_final and transcript:
            # Lưu transcript vào đối tượng socket wrapper để sau này truy xuất
            if not hasattr(deepgram_socket, "_transcript"):
                deepgram_socket._transcript = ""
            # Thêm transcript vào chuỗi đã tích lũy, thêm dấu cách để ngăn cách các đoạn
            deepgram_socket._transcript += ((" " + transcript) if deepgram_socket._transcript else transcript)
            logger.info(f"Final transcript accumulated: {deepgram_socket._transcript}")
        
        payload = {
            'result_id': result_id,
            'speaker': speaker,
            'transcript': transcript,
            'start': start_ts,
            'end': end_ts,
            'is_final': is_final,
            'speech_final': speech_final,
        }
        if confidence is not None:
            payload['confidence'] = float(confidence)

        await fast_socket.send_json(payload)
        # # Save transcrip to database
        # try:
        #     # Generatre unique IDs for the response
        #     response_id = str(uuid.uuid4())

        #      # Create session ID based on date if not provided (you might want to use an actual session ID)
        #     session_id = getattr(fast_socket, "session_id", 
        #                        f"meeting_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            
        #     # Format as markdown for consistency
        #     markdown_content = f"**Speaker {speaker}** [{start_ts} - {end_ts}]:\n{transcript}"

        #     # Create response model 
        #     response = responseModel(
        #         responseId=response_id,
        #         modelId="deepgram-live",
        #         sender=f"speaker_{speaker}",
        #         message=transcript,
        #         session=session_id,
        #         parentResponseId=None, # TODO: link to previous if needed
        #         files=[],
        #         createdAt=datetime.now().isoformat(),
        #         citations=None,
        #         markdown_content=markdown_content
        #     )

        #     # Insert response into database
        #     await insert_response(response)

        # except Exception as e:
        #     logger.error(f"Error saving transcript to database: {e}")

    deepgram_socket = await connect_to_deepgram(get_transcript)
    return deepgram_socket

async def connect_to_deepgram(transcript_received_handler: Callable[[Any], None]):
    language = (os.getenv("DEEPGRAM_LANGUAGE") or "vi").strip()
    logger.info("====== Connecting to Deepgram with language: %s ======", language)
    if not language:
        language = None

    default_model = "nova-2-general" if language and language.lower() != "en" else "nova-2"
    model = (os.getenv("DEEPGRAM_MODEL") or default_model).strip() or default_model

    options = {
        "model": model,
        "smart_format": True,
        "punctuate": True,
        "diarize": False,
        "interim_results": True,
        "utterance_end_ms": 1000,
        "vad_events": True,
        "endpointing": 800,
    }

    if language:
        options["language"] = language
    # Example for raw PCM 16k mono:
    # options["encoding"] = "linear16"
    # options["sample_rate"] = 16000
    # If your client sends WebM/Opus (typical from MediaRecorder):
    # options["encoding"] = "opus"
    # options["sample_rate"] = 48000

    socket_context = dg_client.listen.v1.connect(**options)

    try:
        socket = await socket_context.__aenter__()
    except Exception as exc:
        with suppress(Exception):
            await socket_context.__aexit__(type(exc), exc, None)
        raise Exception(f'Could not open socket: {exc}') from exc

    async def on_message(message: Any):
        if isinstance(message, ListenV1ResultsEvent):
            await transcript_received_handler(message)
        else:
            logger.debug("Deepgram event: %s", getattr(message, "type", type(message)))

    async def on_close(_):
        logger.info('Deepgram WS closed')

    async def on_error(error):
        logger.error('Deepgram WS error: %s', error)

    async def on_open(_):
        logger.info('Deepgram WS opened')

    socket.on(EventType.OPEN, on_open)
    socket.on(EventType.MESSAGE, on_message)
    socket.on(EventType.CLOSE, on_close)
    socket.on(EventType.ERROR, on_error)

    try:
        listener_task = asyncio.create_task(socket.start_listening())
    except Exception as exc:
        with suppress(Exception):
            await socket_context.__aexit__(type(exc), exc, None)
        raise

    return DeepgramSocketWrapper(
        context_manager=socket_context,
        socket=socket,
        listener_task=listener_task,
    )


