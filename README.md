# Meeting Assistant

![Meeting Assistant](./images/meeting_assistant.png)

## Overview
Meeting Assistant is a real‑time meeting intelligence platform providing live speech transcription, speaker diarization, AI summaries, action items, sentiment analysis, topic segmentation, and unified analytical querying across structured + unstructured meeting data.

## Features
- Live Speech-to-Text (browser microphone → WebSocket)
- Speaker Diarization (who spoke when)
- Real-time Transcript Stream
- AI Summaries (abstract + key points)
- Action Items Extraction
- Sentiment & Topic Segmentation (chaptering)
- DOCX Export (formatted meeting minutes)
- Chunked Long-Meeting Processing
- OpenAI (GPT-4) / LLM Integration
- MongoDB Persistence (transcripts, speakers, sessions, conversation history)
- Data Lake Integration (MinIO object storage)
- Query Layer (Trino over Hive Metastore + MongoDB + Postgres)
- Extensible Architecture for Embeddings / Vector Index (future)
- Docker Compose Orchestration

## Architecture

### 1. Application Layer
Flow: Browser Mic → WebSocket (/meeting) → STT (Deepgram or similar) → Diarization → LLM Pipeline (summary, sentiment, topics, action items) → Persistence.
Outputs:
- Real-time transcript turns
- Speaker-attributed segments
- AI metadata (summary, chapters, tasks)
- Exportable minutes (DOCX)

### 2. Storage Layer
- MongoDB: session metadata, transcript turns, speaker mapping, AI responses.
- MinIO (S3-compatible): raw audio, optional video, serialized transcripts (JSON / Parquet), future embeddings.
- (Optional) Future vector store (Milvus / pgvector) for semantic search.

### 3. Metadata & Query Layer
- Hive Metastore (Postgres-backed): table + schema metadata for lake objects in MinIO.
- Trino: federated SQL over Hive (MinIO), MongoDB, Postgres.
- Offline-FS (Postgres): auxiliary analytical or synthetic test data.
- DBeaver / any SQL client: BI & cross-source analytics.

### 4. Data Flow Summary
1. Capture meeting → stream audio
2. STT + diarization produce interim + final transcript segments
3. Segments buffered → chunked → LLM summarization & enrichment
4. Persist:
   - MongoDB: structured meta + turns
   - MinIO: audio object + exported artifacts
5. Optional ETL → Hive external tables (point to MinIO objects)
6. Query with Trino (JOIN transcripts + metadata + external sources)

### 5. Component Responsibilities
| Component       | Role |
|-----------------|------|
| FastAPI Backend | WebSocket handling, orchestration |
| Deepgram / STT  | Streaming transcription |
| Diarization     | Speaker segmentation (pyannote or similar) |
| LLM             | Summaries, actions, sentiment, topics |
| MongoDB         | Operational datastore |
| MinIO           | Durable object store |
| Hive Metastore  | Table metadata for lake |
| Trino           | Unified SQL engine |
| Postgres (meta) | Hive metastore backend |
| Offline-FS DB   | Auxiliary domain data |
| DBeaver         | Analyst SQL client |

## Repository Layout (key)
```
meeting_assistant/
  main.py                 # FastAPI entry
  templates/              # Frontend templates
  static/                 # JS/CSS
  modules/                # Processing, DB access, LLM logic
  models/                 # Diarization assets / RTTM
  trino/
    catalog/*.properties  # Trino connectors (mongodb, hive, postgresql)
  docker-compose.yml
  .env
```

## Getting Started

### 1. Install Python Dependencies
```
pip install -r requirements.txt
```

### 2. Run API (dev)
```
uvicorn main:app --reload
```
Visit: http://127.0.0.1:8000/  
Grant microphone permission.

### 3. Environment Variables (.env)
```
MONGO_URI=mongodb://quanmd:quanmd@localhost:27017/
OPENAI_API_KEY=your_key_here
# Add others as needed
```

### 4. Start Infrastructure (MongoDB only)
```
docker-compose up -d mongodb
```

### 5. Start Full Analytics Stack
```
docker-compose up -d
```
Services:
- MongoDB: 27017
- Trino: 8080
- MinIO: 9000 (API), 9001 (Console)
- Hive Metastore: 9083
- Postgres Metastore DB: 5433
- Offline-FS DB: 5434

### 6. Access MinIO
Browser: http://localhost:9001  
Credentials: minio_access_key / minio_secret_key  
Create bucket (e.g. meetings/) for audio + transcript exports.

### 7. Trino Catalogs (examples)
`trino/catalog/mongodb.properties`
```
connector.name=mongodb
connection-url=mongodb://quanmd:quanmd@mongodb:27017/
connection-user=quanmd
connection-password=quanmd
```
`trino/catalog/mle.properties` (Hive over MinIO)
```
connector.name=hive
hive.metastore.uri=thrift://hive-metastore:9083
hive.s3.endpoint=http://minio:9000
hive.s3.aws-access-key=minio_access_key
hive.s3.aws-secret-key=minio_secret_key
hive.allow-drop-table=true
```

### 8. Creating External Tables (Example)
After exporting a Parquet transcript to `s3://meetings/transcripts/2025-01-01/part-0.parquet` (MinIO path):
In Trino:
```
CREATE SCHEMA IF NOT EXISTS hive.meetings WITH (location='s3a://meetings/');
CREATE TABLE hive.meetings.transcripts (
  session_id varchar,
  speaker varchar,
  start_time double,
  end_time double,
  text varchar
)
WITH (
  external_location='s3a://meetings/transcripts/2025-01-01/',
  format='PARQUET'
);
```

### 9. Query Examples
Join diarized transcript (Hive) with conversation metadata (MongoDB):
```
SELECT t.session_id,
       t.speaker,
       t.text,
       m.summary
FROM hive.meetings.transcripts t
LEFT JOIN mongodb.meeting_assistant.conversation_metadata m
       ON t.session_id = m.session_id
WHERE t.speaker <> 'UNKNOWN';
```

### 10. Development Notes
- Use virtual environment
- Keep long LLM calls async or offloaded
- Batch summarize after N segments (configurable)
- Persist raw + enriched forms

### 11. Testing (Example)
```
pytest -q
```
Mock MongoDB in unit tests using `unittest.mock` or `mongomock`.

### 12. Diarization (AMI Mini Example)
```
git clone https://github.com/pyannote/AMI-diarization-setup.git
cd AMI-diarization-setup/pyannote/
bash download_ami_mini.sh
```
Produces `.wav` + `.rttm` for evaluation.

### 13. Security & Production Considerations
- Add auth (JWT) for WebSocket + API
- Rate limit transcript events
- Rotate API keys & secrets
- Use MinIO buckets with policies
- Add indexing on MongoDB (session_id, timestamps)

### 14. Roadmap (Suggested)
- Embedding generation & semantic search
- Vector store integration
- Multi-language diarization
- Real-time topic drift detection
- Analytics dashboards (Trino → BI)

## Troubleshooting
- WebSocket 400: confirm correct ws:// endpoint and binary audio frames
- Duplicate container names: `docker rm -f <name>`
- Mongo auth failures: ensure auth DB = admin (for root), correct URI
- Trino cannot see Hive tables: check metastore logs + MinIO connectivity

## References
- AMI Corpus: http://groups.inf.ed.ac.uk/ami/corpus/
- pyannote.audio: https://github.com/pyannote/pyannote-audio
- Trino Docs: https://trino.io/docs/
- MinIO: https://min.io
- FastAPI: https://fastapi.tiangolo.com