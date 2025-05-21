"""
Base Celery task classes for DZ Bus Tracker.
"""
import logging

from celery import Task
from django.conf import settings

logger = logging.getLogger(__name__)


class BaseTask(Task):
    """
    Base task class with common functionality.
    """
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Handle task failure.
        """
        logger.error(
            f"Task {self.name} ({task_id}) failed: {exc}",
            exc_info=einfo,
        )

        # Log to Sentry if configured
        if hasattr(settings, "SENTRY_DSN") and settings.SENTRY_DSN:
            try:
                import sentry_sdk

                with sentry_sdk.push_scope() as scope:
                    scope.set_tag("task_id", task_id)
                    scope.set_tag("task_name", self.name)
                    scope.set_context("task_args", args)
                    scope.set_context("task_kwargs", kwargs)
                    sentry_sdk.capture_exception(exc)
            except ImportError:
                pass

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """
        Handle task retry.
        """
        logger.warning(
            f"Task {self.name} ({task_id}) retrying: {exc}",
            exc_info=einfo,
        )

    def on_success(self, retval, task_id, args, kwargs):
        """
        Handle task success.
        """
        logger.info(f"Task {self.name} ({task_id}) succeeded")

    def apply_async(self, args=None, kwargs=None, **options):
        """
        Apply task asynchronously with additional logging.
        """
        logger.debug(f"Scheduling task {self.name}")
        return super().apply_async(args, kwargs, **options)


class LoggedTask(BaseTask):
    """
    Task class with more detailed logging.
    """
    abstract = True

    def __call__(self, *args, **kwargs):
        """
        Execute task with detailed logging.
        """
        logger.info(f"Starting task {self.name}")
        start_time = self.now()

        try:
            result = super().__call__(*args, **kwargs)
            end_time = self.now()

            duration = end_time - start_time
            logger.info(
                f"Task {self.name} completed in {duration:.2f}s"
            )

            return result
        except Exception as e:
            end_time = self.now()
            duration = end_time - start_time

            logger.error(
                f"Task {self.name} failed after {duration:.2f}s: {e}"
            )
            raise

    def now(self):
        """
        Get current time in seconds.
        """
        import time
        return time.time()


class DatabaseTask(LoggedTask):
    """
    Task class for database operations with connection management.
    """
    abstract = True

    def __call__(self, *args, **kwargs):
        """
        Execute task with database connection management.
        """
        from django.db import connection, connections

        # Close any existing connections
        connections.close_all()

        try:
            result = super().__call__(*args, **kwargs)
            return result
        finally:
            # Always close connections at the end
            connections.close_all()


class RetryableTask(DatabaseTask):
    """
    Task class with automatic retrying.
    """
    abstract = True

    # Default retry settings
    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes
    retry_jitter = True