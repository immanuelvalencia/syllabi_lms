from threading import Thread

from django.utils import timezone

from .models import AiToolRequest


def enqueue_ai_tool_request(request_id):
    Thread(target=_send_ai_task, args=(request_id,), daemon=True).start()


def _send_ai_task(request_id):
    try:
        from .tasks import run_ai_tool_request

        run_ai_tool_request.delay(request_id)
    except Exception as exc:
        AiToolRequest.objects.filter(pk=request_id).update(
            status=AiToolRequest.Status.FAILED,
            error_message=str(exc),
            completed_at=timezone.now(),
        )
