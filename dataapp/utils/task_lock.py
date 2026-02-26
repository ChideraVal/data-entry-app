from django.utils import timezone
from django.db import transaction
from ..models import TaskLock


class TaskAlreadyRunning(Exception):
    pass


def acquire_lock(name: str, timeout_minutes=10):
    """
    Acquire a lock or raise TaskAlreadyRunning.
    If lock is stale (older than timeout), it will be released and reopened.
    """
    now = timezone.now()

    with transaction.atomic():
        lock, _ = TaskLock.objects.select_for_update().get_or_create(name=name)

        # If locked and NOT stale → block
        if lock.is_locked and lock.locked_at and \
           (now - lock.locked_at).total_seconds() < timeout_minutes * 60:
            raise TaskAlreadyRunning(f"Task '{name}' is already running.")

        # Acquire lock (fresh or stale)
        lock.is_locked = True
        lock.locked_at = now
        lock.save()


def release_lock(name: str):
    with transaction.atomic():
        lock = TaskLock.objects.select_for_update().get(name=name)
        lock.is_locked = False
        lock.locked_at = None
        lock.save()
