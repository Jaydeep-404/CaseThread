import logging
from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

logger = logging.getLogger(__name__)


class DatabaseHelper:
    _instance = None
    _db = None
    _client = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def db(self):
        return self._db
    
    @db.setter
    def db(self, value):
        self._db = value
    
    @property
    def client(self):
        return self._client
    
    @client.setter
    def client(self, value):
        self._client = value

db = DatabaseHelper.get_instance()

async def connect_to_mongodb():
    """Connect to MongoDB."""    
    # Try to connect to MongoDB
    try:
        logger.info("Connecting to MongoDB...")
        # Simple connection to MongoDB using the connection string from settings
        db.client = AsyncIOMotorClient(settings.MONGODB_URL)
        
        # Get database connection
        db.db = db.client[settings.MONGODB_DB_NAME]
        logger.info("Connected to MongoDB")
    except Exception as e:
        logger.error(f"Could not connect to MongoDB: {str(e)}")
        

async def close_mongodb_connection():
    """Close MongoDB connection."""
    logger.info("Closing MongoDB connection...")
    if db.client:
        db.client.close()
        logger.info("MongoDB connection closed")


async def get_database():
    """Get database connection."""
    return db.db
