import threading
import time
import uuid

_jobs = {}
_lock = threading.Lock()

# Completed/failed jobs older than this are pruned on the next create_job()
# call, so the in-memory store doesn't grow forever on a long-running server.
_MAX_AGE_SECONDS = 60 * 60


def _prune_locked():
    now = time.time()
    expired = [
        job_id
        for job_id, job in _jobs.items()
        if job["status"] in ("completed", "failed") and now - job["created_at"] > _MAX_AGE_SECONDS
    ]
    for job_id in expired:
        del _jobs[job_id]


def create_job():
    job_id = str(uuid.uuid4())
    with _lock:
        _prune_locked()
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "running",
            "processed": 0,
            "total": None,
            "result": None,
            "file_bytes": None,
            "file_name": None,
            "file_media_type": None,
            "error": None,
            "created_at": time.time(),
        }
    return job_id


def update_progress(job_id, processed, total=None):
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job["processed"] = processed
            if total is not None:
                job["total"] = total


def progress_callback_for(job_id):
    def callback(processed, total=None):
        update_progress(job_id, processed, total)

    return callback


def complete_job(job_id, result, file_bytes=None, file_name=None, file_media_type="application/octet-stream"):
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job["status"] = "completed"
            job["result"] = result
            job["file_bytes"] = file_bytes
            job["file_name"] = file_name
            job["file_media_type"] = file_media_type
            if job["total"] is not None:
                job["processed"] = job["total"]


def fail_job(job_id, error):
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job["status"] = "failed"
            job["error"] = error


def get_job(job_id):
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def run_in_background(run):
    """`run(job_id)` does the work and must itself call complete_job/fail_job
    (rather than just returning a value) so it can attach downloadable file
    bytes alongside the JSON-safe result. Runs in a daemon thread that keeps
    going to completion even if nothing is left listening for the response —
    a page refresh or a closed connection does not stop it.
    """
    job_id = create_job()

    def target():
        try:
            run(job_id)
        except Exception as exc:
            fail_job(job_id, str(exc))

    threading.Thread(target=target, daemon=True).start()
    return job_id


# Finished jobs (including any cached file bytes) are only pruned lazily on
# the next create_job() call above, which does nothing if no new job ever
# starts. This janitor sweeps on a timer instead, so completed/failed jobs
# never sit in memory for longer than _MAX_AGE_SECONDS regardless of traffic.
_JANITOR_INTERVAL_SECONDS = 5 * 60


def _janitor_loop():
    while True:
        time.sleep(_JANITOR_INTERVAL_SECONDS)
        with _lock:
            _prune_locked()


threading.Thread(target=_janitor_loop, daemon=True).start()
