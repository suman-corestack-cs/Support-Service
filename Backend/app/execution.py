import datetime
import json
import queue
import threading


def _json_default(value):
    """Fallback for objects plain json.dumps can't serialize on its own —
    boto3 responses commonly include real datetime/date objects (e.g. RI
    Start/End fields), which would otherwise raise mid-stream and abort the
    response instead of cleanly reaching a "completed"/"failed" line."""
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return str(value)


def stream(run):
    """Run a script in a background thread and stream its progress as NDJSON.

    `run` is called as `run(progress_callback)` and must return the script's
    result. Everything is delivered over a single HTTP response body: zero or
    more `{"status": "running", ...}` lines while it executes, followed by
    exactly one final `{"status": "completed", "result": ...}` or
    `{"status": "failed", "error": ...}` line.
    """
    updates = queue.Queue()

    def progress_callback(processed, total=None):
        updates.put({"status": "running", "processed": processed, "total": total})

    def target():
        try:
            result = run(progress_callback)
            updates.put({"status": "completed", "result": result})
        except Exception as exc:
            updates.put({"status": "failed", "error": str(exc)})
        finally:
            updates.put(None)

    threading.Thread(target=target, daemon=True).start()

    def generator():
        while True:
            item = updates.get()
            if item is None:
                return
            yield json.dumps(item, default=_json_default) + "\n"

    return generator()
