# main.py (python example)

import os
import logging
from deepgram.utils import verboselogs

from deepgram import (
    DeepgramClient,
    PrerecordedOptions,
    FileSource,
)

# Import dependencies and set up the main function
import requests
import wave
import io
import time
import os
import json
import threading
from datetime import datetime

from deepgram.clients.agent.v1.websocket.options import SettingsOptions


AUDIO_URL = {
    "url": "https://dpgr.am/bueller.wav"
}

def format_timestamp(seconds):
    """Format seconds to HH:MM:SS.mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:06.3f}"

def speaker_diarization(audio_file):
    """
    Perform speaker diarization on the given audio file.
    """
    # Initialize Deepgram client
    deepgram = DeepgramClient(api_key="40b0ee1c693850eb77945a13526e00f51037deec")

    print("Reading audio file...")
    with open(audio_file, 'rb') as f:
        buffer_data = f.read()

    payload: FileSource = {
        "buffer": buffer_data
    }

    # Set up options for speaker diarization
    options = PrerecordedOptions(
        model="nova-3",
        smart_format=True,
        diarize=True,
        paragraphs=True,
    )

    # Call the transcribe_file method with the text payload and options  
    print("Calling Deepgram...")  
    response = deepgram.listen.rest.v("1").transcribe_file(payload, options)  
  
    return response

def export_transcript(response_data, output_file):  
    """Export transcript with formatting to a text file"""  
    with open(output_file, "w") as f:  
        f.write("=== TRANSCRIPT ===\n\n")  
  
        # Access the transcript data  
        results = response_data.get("results", {})  
        channels = results.get("channels", [])  
  
        if not channels or not channels[0].get("alternatives"):  
            f.write("No transcript data found.\n")  
            return  
  
        # Get the paragraphs data if available  
        paragraphs = channels[0]["alternatives"][0].get("paragraphs", {}).get("paragraphs", [])  
  
        if paragraphs:  
            # Format with paragraphs and speakers  
            for i, para in enumerate(paragraphs):  
                speaker = f"Speaker {para.get('speaker', '?')}"  
                start_time = format_timestamp(para.get("start", 0))  
  
                f.write(f"[{start_time}] {speaker}:\n")  
  
                for sentence in para.get("sentences", []):  
                    f.write(f"  {sentence.get('text', '')}\n")  
  
                f.write("\n")  
        else:  
            # Fallback to flat transcript if no paragraphs  
            transcript = channels[0]["alternatives"][0].get("transcript", "")  
            f.write(transcript)  
  
        f.write("\n=== END OF TRANSCRIPT ===\n")

def main():
    try:
        audio_file = "/home/quandm/quandm/agent-be/premier_broken-phone.mp3"  # Path to your audio file
        response = speaker_diarization(audio_file)
        print(f"response: {response}\n\n")
        export_transcript(response.to_dict(), "./transcript.txt")
        print(f"Transcript exported successfully to ./transcript.txt")

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    main()
