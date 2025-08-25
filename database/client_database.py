from pymongo import MongoClient, AsyncMongoClient
from dotenv import load_dotenv
import os

load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI, uuidRepresentation="standard")
aclient = AsyncMongoClient(MONGO_URI, uuidRepresentation="standard")