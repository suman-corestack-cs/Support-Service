import itertools
import json
from typing import Any, Dict, List, Literal, Optional

from bson import json_util
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import execution
from app.mongo_config import available_regions, get_database

router = APIRouter(prefix="/mongo", tags=["Mongo"])

MAX_LIMIT = 1000

# Operators that either execute arbitrary server-side JavaScript ($where,
# $function, $accumulator) or write/mutate data ($out, $merge). Blocking them
# keeps this a strictly read-only, query-only endpoint.
_FORBIDDEN_OPERATORS = {"$where", "$function", "$accumulator", "$out", "$merge"}


def _assert_read_only(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in _FORBIDDEN_OPERATORS:
                raise ValueError(f"Operator '{key}' is not allowed on this read-only query endpoint.")
            _assert_read_only(nested)
    elif isinstance(value, list):
        for item in value:
            _assert_read_only(item)


def _to_jsonable(value):
    """Converts BSON types (ObjectId, datetime, Decimal128, ...) to plain
    JSON-safe values, using MongoDB's Extended JSON rules for the encoding
    step but the *plain* json module to parse it back — bson.json_util.loads
    would just reconstruct the original ObjectId/datetime objects, which
    defeats the point."""
    return json.loads(json_util.dumps(value))


def _from_jsonable(value):
    """Inverse of _to_jsonable, for filters/pipelines coming *in*: hydrates
    MongoDB Extended JSON markers (e.g. {"$oid": "<hex>"} for ObjectId) sent
    as plain JSON back into real BSON types, so callers can filter on
    ObjectId fields (e.g. {"tenant_id": {"$oid": "..."}}) without a bespoke
    ID-string convention. Run _assert_read_only on the value *before* this —
    hydration can turn a plain dict into a non-dict BSON object, which would
    make the forbidden-operator scan silently stop recursing into it."""
    return json_util.loads(json.dumps(value))


class MongoQueryRequest(BaseModel):
    region: str = Field(..., description=f"One of: {', '.join(available_regions())}")
    database: Optional[str] = Field(None, description="Database name; defaults to the URI's default database")
    collection: str
    operation: Literal["find", "aggregate", "count"] = "find"
    filter: Optional[Dict[str, Any]] = Field(None, description="Query filter, used by find/count")
    projection: Optional[Dict[str, Any]] = Field(None, description="Field projection, used by find")
    sort: Optional[List[List[Any]]] = Field(None, description="[[field, 1|-1], ...], used by find")
    limit: int = Field(100, description=f"Max documents returned by find/aggregate (capped at {MAX_LIMIT})")
    pipeline: Optional[List[Dict[str, Any]]] = Field(None, description="Aggregation pipeline, used by aggregate")


def run_mongo_query(request: MongoQueryRequest, progress_callback=None):
    limit = max(1, min(request.limit, MAX_LIMIT))

    db = get_database(request.region, request.database)
    collection = db[request.collection]

    if request.operation == "aggregate":
        _assert_read_only(request.pipeline or [])
        pipeline = _from_jsonable(request.pipeline or [])
        cursor = collection.aggregate(pipeline)
        documents = list(itertools.islice(cursor, limit))
        result = {"documents": _to_jsonable(documents), "count": len(documents)}

    elif request.operation == "count":
        _assert_read_only(request.filter or {})
        query_filter = _from_jsonable(request.filter or {})
        result = {"count": collection.count_documents(query_filter)}

    else:  # find
        _assert_read_only(request.filter or {})
        query_filter = _from_jsonable(request.filter or {})
        cursor = collection.find(query_filter, projection=request.projection)
        if request.sort:
            cursor = cursor.sort([tuple(item) for item in request.sort])
        documents = list(itertools.islice(cursor, limit))
        result = {"documents": _to_jsonable(documents), "count": len(documents)}

    if progress_callback:
        progress_callback(1, 1)

    return result


@router.post("/query")
def query_mongo(request: MongoQueryRequest):
    def run(progress_callback):
        return run_mongo_query(request, progress_callback)

    return StreamingResponse(execution.stream(run), media_type="application/x-ndjson")
