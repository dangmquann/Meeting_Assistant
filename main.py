import os
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from api_routers import ping, meeting

load_dotenv()

app = FastAPI(
    title="Meeting Assistant API",
    description="API for transcribing meetings and generating summaries",
    version="0.1.0"
)

# Configure logging
logger = logging.getLogger("meeting_assistant")
logger.setLevel(logging.INFO)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(ping.router, tags=["Health"])
app.include_router(meeting.router, tags=["Meeting"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)