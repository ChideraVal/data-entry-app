# from django.core.management.base import BaseCommand
# from django.utils import timezone
# from ...utils.email_monitor import fetch_new_emails
# from ...utils.task_lock import acquire_lock, release_lock, TaskAlreadyRunning


# class Command(BaseCommand):
#     help = "Fetch and process incoming order emails"

#     def handle(self, *args, **options):
#         lock_name = "fetch_emails_lock"

#         # Try to acquire lock
#         try:
#             acquire_lock(lock_name, timeout_minutes=10)
#         except TaskAlreadyRunning:
#             self.stdout.write(self.style.WARNING(
#                 f"[{timezone.now()}] Skipping fetch: another instance is already running."
#             ))
#             return

#         self.stdout.write(self.style.SUCCESS(
#             f"[{timezone.now()}] Starting email fetch..."
#         ))

#         try:
#             # Run your actual email fetch
#             fetched_count = fetch_new_emails()
#             self.stdout.write(self.style.SUCCESS(
#                 f"{fetched_count} emails fetched at {timezone.now()}"
#             ))

#         except Exception as e:
#             self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
#             raise e

#         finally:
#             # Release the lock so the next cron run can execute
#             release_lock(lock_name)
#             self.stdout.write(self.style.SUCCESS(
#                 f"[{timezone.now()}] Email fetch finished, lock released."
#             ))



from django.core.management.base import BaseCommand
from django.utils import timezone
from ...utils.task_lock import acquire_lock, release_lock, TaskAlreadyRunning
from ...utils.email_monitor import fetch_and_process_emails

class Command(BaseCommand):
    help = "Fetch emails and process AI-extracted orders"

    def handle(self, *args, **options):
        lock_name = "fetch_emails_lock"

        try:
            acquire_lock(lock_name, timeout_minutes=10)
        except TaskAlreadyRunning:
            self.stdout.write(self.style.WARNING(
                f"[{timezone.now()}] Skipping fetch: another instance is already running."
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"[{timezone.now()}] Starting email fetch and AI processing..."
        ))

        try:
            ENVIRONMENT_ID = 18
            # fetched_count, skipped_count, processed_count, failed_count = fetch_and_process_emails(ENVIRONMENT_ID)
            fetched_count = fetch_and_process_emails(ENVIRONMENT_ID)

            # self.stdout.write(self.style.SUCCESS(
            #     f"[{timezone.now()}] Emails fetched: {fetched_count + skipped_count}, "
            #     f"[{timezone.now()}] Emails processed: {fetched_count}, "
            #     f"[{timezone.now()}] Emails skipped (max size): {skipped_count}, "
            #     f"Success: {processed_count}, Failed: {failed_count}"
            # ))
            
            self.stdout.write(self.style.SUCCESS(
                f"[{timezone.now()}] Emails fetched: {fetched_count}"
            ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
            raise e

        finally:
            release_lock(lock_name)
            self.stdout.write(self.style.SUCCESS(
                f"[{timezone.now()}] Email fetch finished, lock released."
            ))
