# Meeting_Assistant
![Meeting Assistant](./images/meeting_assistant.png)
## Features

- **Live Speech-to-Text**: Real-time transcription of meeting audio via browser microphone.
- **Speaker Diarization**: Identifies and labels different speakers in the transcript.
- **Meeting Minutes Generation**: Automatically generates structured meeting minutes including:
  - Abstract summary
  - Key points
  - Action items
  - Sentiment analysis
  - Chapters/topics with timestamps and key points
- **Export to DOCX**: Save meeting minutes as a formatted Word document.
- **Chunked Processing**: Handles long meetings by chunking transcripts for summarization and extraction.
- **OpenAI GPT-4 Integration**: Uses GPT-4 for advanced summarization, key point extraction, and sentiment analysis.
- **Browser-based UI**: Simple web interface for starting and viewing live transcriptions.
- **Microphone Access**: Works directly from your browser, no extra software needed.

## Getting Started

Make sure your virtual environment is activated and install the dependencies in the requirements.txt file inside. 

```
pip install -r requirements.txt
```

Make sure you're in the directory with the **main.py** file and run the project in the development server.

```
uvicorn main:app --reload
```

Pull up a browser and go to your localhost, http://127.0.0.1:8000/.

Allow access to your microphone and start speaking. A transcript of your audio will appear in the