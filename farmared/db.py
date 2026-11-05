"""Conexiones a MongoDB y Redis. Se crean una sola vez y se reusan."""
import redis
from pymongo import MongoClient

from farmared import config

_mongo_client = None
_redis = None


def get_mongo_client():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
    return _mongo_client


def get_db():
    return get_mongo_client()[config.MONGO_DB]


def get_redis():
    global _redis
    if _redis is None:
        _redis = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    return _redis
