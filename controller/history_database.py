import os
import logging
from pydantic import BaseModel
from pymongo import MongoClient
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from controller.utils import normalize_http_exception
from dotenv import load_dotenv
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
history_collection = client["meeting_assistant"]["history_conversation"]

class responseModel(BaseModel):
    responseId: str
    modelId: str
    sender: str
    message: str | None = None
    session: str
    parentResponseId: str | None
    files: List[str] = []
    createdAt: str
    citations: Optional[List[Dict[str, Any]]] = None
    markdown_content: str | None = None



def insert_response(response: responseModel):
    try:
        # Convert the ISO format string to datetime before saving to MongoDB
        response_dict = response.model_dump()
        if response_dict.get("createdAt"):
            response_dict["createdAt"] = datetime.fromisoformat(
                response_dict["createdAt"]
            )

        result = history_collection.insert_one(response_dict)
        return result.acknowledged
    except Exception as e:
        raise normalize_http_exception(e)

if __name__ == "__main__":
    # Example test data
    test_response = responseModel(
        responseId="r1",
        modelId="gpt-4",
        sender="human",
        message="Hello",
        session="s1",
        parentResponseId=None,
        files=[],
        createdAt=datetime.now().isoformat(),
        citations=None,
        markdown_content=None,
    )
    success = insert_response(test_response)
    print("Insert successful:", success)