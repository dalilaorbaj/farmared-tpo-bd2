import os

from dotenv import load_dotenv

# si existe un .env (corriendo local) lo levanta, en codespaces ya vienen del compose
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/?directConnection=true")
MONGO_DB = os.getenv("MONGO_DB", "farmared")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
