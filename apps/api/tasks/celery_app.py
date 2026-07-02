from celery import Celery
from celery.schedules import crontab
from kombu import Queue
from kombu.exceptions import OperationalError

try:
    from ..config import settings
except ImportError:
    from config import settings

celery_app = Celery(
    "freeframe",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "apps.api.tasks.transcode_tasks",
        "apps.api.tasks.watermark_tasks",
        "apps.api.tasks.reminder_tasks",
        "apps.api.tasks.email_tasks",
        "apps.api.tasks.drive_sync_tasks",
        "apps.api.tasks.autotag_tasks",
    ],
)

# Register this as Celery's process-global default app. A @shared_task resolves its app
# from a THREAD-LOCAL "current app"; a freshly spawned thread (e.g. the daemon thread in
# send_task_safe below) has none, so without this it falls back to Celery's built-in
# amqp:// placeholder broker and every publish fails with Connection refused — silently,
# because _dispatch_task swallows it. set_default() makes threads with no thread-local
# binding resolve to this Redis-backed app instead.
celery_app.set_default()

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=5,
    broker_pool_limit=0,  # Disable connection pooling in web process to avoid stale connections
    # Redis re-delivers an unacked (acks_late) task after this many seconds, assuming the
    # worker died. Transcodes can run up to 4h (ffmpeg subprocess timeout 14400s); the
    # default visibility_timeout of 1h would re-deliver long transcodes mid-flight, cloning
    # them onto the queue and pinning every worker slot. Keep it safely above the max run time.
    broker_transport_options={"visibility_timeout": 21600},  # 6h
    # Define queues
    task_queues=(
        Queue("default"),
        Queue("transcoding_priority"),
        Queue("transcoding"),
        Queue("drive_sync"),
        Queue("email_high"),  # Magic codes, invites - immediate
        Queue("email_low"),   # Mentions, comments - can be delayed
    ),
    task_default_queue="default",
    # Route tasks to queues
    task_routes={
        "apps.api.tasks.transcode_tasks.*": {"queue": "transcoding"},
        "apps.api.tasks.drive_sync_tasks.*": {"queue": "drive_sync"},
        "apps.api.tasks.email_tasks.send_magic_code_email": {"queue": "email_high"},
        "apps.api.tasks.email_tasks.send_invite_email": {"queue": "email_high"},
        "apps.api.tasks.email_tasks.send_mention_email": {"queue": "email_low"},
        "apps.api.tasks.email_tasks.send_comment_email": {"queue": "email_low"},
        "apps.api.tasks.email_tasks.send_assignment_email": {"queue": "email_low"},
        "apps.api.tasks.email_tasks.send_share_email": {"queue": "email_low"},
        "apps.api.tasks.email_tasks.send_approval_email": {"queue": "email_low"},
        "apps.api.tasks.email_tasks.send_project_added_email": {"queue": "email_low"},
    },
    # Rate limiting for email queues (SES limits)
    task_annotations={
        "apps.api.tasks.email_tasks.*": {"rate_limit": "10/s"},  # 10 emails per second
    },
)

celery_app.conf.beat_schedule = {
    "due-date-reminders": {
        "task": "send_due_date_reminders",
        "schedule": crontab(minute="0"),  # every hour
    },
    "drive-sync": {
        "task": "apps.api.tasks.drive_sync_tasks.sync_drive_connections",
        "schedule": crontab(minute="0"),  # hourly
    },
    "recover-stalled-assets": {
        "task": "apps.api.tasks.transcode_tasks.recover_stalled_assets",
        "schedule": crontab(minute="*/5"),  # every 5 minutes
        # Run the lightweight maintenance sweep on `default`, NOT `transcoding`. On the
        # heavy queue it queues up behind slow transcodes and, when slots stall, beat keeps
        # appending it every 5 min — the backlog that buried real jobs ~5000-deep.
        "options": {"queue": "default"},
    },
}


import threading
import logging

_task_logger = logging.getLogger("celery.dispatch")


def _dispatch_task(task, args, kwargs, queue=None):
    """Actually send the task to Celery broker (runs in background thread)."""
    try:
        task.apply_async(args=args, kwargs=kwargs, queue=queue)
    except (OperationalError, ConnectionError, OSError):
        try:
            with celery_app.producer_or_acquire() as producer:
                task.apply_async(args=args, kwargs=kwargs, queue=queue, producer=producer)
        except Exception:
            _task_logger.warning("Failed to dispatch task %s after retry", task.name)
    except Exception:
        _task_logger.warning("Failed to dispatch task %s", task.name)


def send_task_safe(task, *args, queue=None, **kwargs):
    """Send a Celery task in a background thread so it never blocks the API response.

    Broker connections can take seconds (especially with pool_limit=0).
    This ensures the API returns immediately while the task is dispatched async.
    Pass queue= to route to a specific queue (e.g. "transcoding_priority").
    """
    thread = threading.Thread(
        target=_dispatch_task,
        args=(task, args, kwargs, queue),
        daemon=True,
    )
    thread.start()
