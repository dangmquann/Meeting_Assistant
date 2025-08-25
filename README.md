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
- **MongoDB Integration**: Stores meeting transcripts, speaker data, and conversation history in MongoDB for persistence and later retrieval.

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

### Running MongoDB with Docker Compose

You can quickly start a MongoDB service using Docker Compose.

To start MongoDB, run:

```bash
docker-compose up -d
```

Your MongoDB instance will be available at `localhost:27017` with username `quanmd` and password `quanmd`.

Update your `.env` file:

```
MONGO_URI=mongodb://quanmd:quanmd@localhost:27017/
```

Now your application can connect to MongoDB using this URI.


# Training Speaker Diarization with AMI Corpus

This guide explains how to prepare and train a speaker diarization model using the AMI Meeting Corpus and pyannote.audio.

## 1. Download AMI Data

Clone the setup repository and download a subset of the AMI corpus:

```bash
git clone https://github.com/pyannote/AMI-diarization-setup.git
cd AMI-diarization-setup/pyannote/
bash download_ami_mini.sh
```

This will download audio files and RTTM annotations for several meetings.
- [AMI Corpus](http://groups.inf.ed.ac.uk/ami/corpus/)
- [pyannote.audio Documentation](https://github.com/pyannote/pyannote-audio)

## 2. Prepare Data

- Audio files are stored in `./models/AMI-diarization-setup/pyannote/<meeting_id>/audio/`.
- RTTM files (speaker labels and segments) are in `./models/AMI-diarization-setup/pyannote/<meeting_id>/`.
- Ensure all audio files are in WAV format and RTTM files are correctly formatted.

## 3. Environment Setup

Install dependencies:

```bash
pip install pyannote.audio
```

(Optional) For GPU support, install PyTorch with CUDA.