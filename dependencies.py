import os
from typing import Dict, Optional, Any, Tuple
import pymongo
from sqlalchemy import create_engine, text
from deepgram import DeepgramClient

async def check_mongodb_health() -> Tuple[str, Optional[str]]:
    try:
        mongodb_uri = os.getenv("MONGO_URI", "mongodb://quanmd:quanmd@mongodb:27017/")
        client = pymongo.MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return "healthy", "Connected successfully"
    except Exception as e:
        return "unhealthy", f"MongoDB connection failed: {str(e)}"
    
async def check_postgres_health() -> Tuple[str, Optional[str]]:
    try:
        conn_string = os.getenv("POSTGRES_DATABASE_URL", "postgresql://quanmd:quanmd@offline-fs:5432/k6")
        engine = create_engine(conn_string)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "healthy", "Connected successfully"
    except Exception as e:
        return "unhealthy", f"Postgres connection failed: {str(e)}"

async def check_deepgram_health() -> Tuple[str, Optional[str]]:
    try:
        api_key = os.getenv("DEEPGRAM_API_KEY")
        if not api_key:
            return "unknown", "No API key configured"
        
        client = DeepgramClient(api_key)
        # Just verify we can create a client (actual API testing would require usage credits)
        return "healthy", "API key configured"
    except Exception as e:
        return "unhealthy", f"Deepgram client error: {str(e)}"

async def get_services_health() -> Dict[str, Any]:
    """Check all service dependencies health."""
    services = {}
    
    # Check MongoDB
    mongo_status, mongo_msg = await check_mongodb_health()
    services["mongodb"] = {"status": mongo_status, "message": mongo_msg}
    
    # Check Postgres
    postgres_status, postgres_msg = await check_postgres_health()
    services["database"] = {"status": postgres_status, "message": postgres_msg}
    
    # Check Deepgram
    deepgram_status, deepgram_msg = await check_deepgram_health()
    services["deepgram"] = {"status": deepgram_status, "message": deepgram_msg}
    
    return services