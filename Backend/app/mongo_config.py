import os
import threading
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

# Load Backend/.env explicitly (not just the process's cwd), so this works
# regardless of where uvicorn was started from. python-dotenv resolves the
# ${US_PASSWORD}-style references inside the Mongo URIs automatically.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

# Region key -> the .env variable holding that region's Mongo connection URI.
MONGO_REGION_ENV_VARS = {
    "us": "MONGO_US_URI",
    "msprod": "MONGO_MSPROD_URI",
    "vlm": "MONGO_VLM_URI",
    "eu": "MONGO_EU_URI",
    "in": "MONGO_IN_URI",
    "mea": "MONGO_MEA_URI",
    "us3": "MONGO_US3_URI",
}

_clients = {}
_clients_lock = threading.Lock()


def available_regions():
    return list(MONGO_REGION_ENV_VARS.keys())


def get_mongo_client(region):
    """Returns a cached, shared MongoClient for the given region, creating it
    on first use. MongoClient manages its own connection pool and is safe to
    share across requests/threads — there's no reason to open a new one per
    call.
    """
    region_key = (region or "").strip().lower()
    env_var = MONGO_REGION_ENV_VARS.get(region_key)
    if not env_var:
        raise ValueError(f"Unknown Mongo region '{region}'. Valid options: {', '.join(available_regions())}")

    uri = os.getenv(env_var)
    if not uri:
        raise ValueError(f"{env_var} is not set in the environment (.env file).")

    with _clients_lock:
        client = _clients.get(region_key)
        if client is None:
            client = MongoClient(uri)
            _clients[region_key] = client
        return client


def get_database(region, database_name=None):
    """Returns a Database handle for the region. Without an explicit
    database_name, falls back to the database named in the connection URI
    (here, the auth database — usually "admin" — since none of the URIs are
    scoped to an app database)."""
    client = get_mongo_client(region)
    if database_name:
        return client[database_name]
    return client.get_default_database()
