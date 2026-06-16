from celery import shared_task
from django.utils import timezone

from .models import AiToolRequest


@shared_task(bind=True, autoretry_for=(TimeoutError,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def run_ai_tool_request(self, request_id):
    ai_request = AiToolRequest.objects.get(pk=request_id)
    ai_request.status = AiToolRequest.Status.RUNNING
    ai_request.started_at = timezone.now()
    ai_request.save(update_fields=["status", "started_at"])

    try:
        result = build_ai_response(ai_request)
    except Exception as exc:
        ai_request.status = AiToolRequest.Status.FAILED
        ai_request.error_message = str(exc)
        ai_request.completed_at = timezone.now()
        ai_request.save(update_fields=["status", "error_message", "completed_at"])
        raise

    ai_request.status = AiToolRequest.Status.COMPLETED
    ai_request.result = result
    ai_request.completed_at = timezone.now()
    ai_request.save(update_fields=["status", "result", "completed_at"])
    return result


def build_ai_response(ai_request):
    prompt = ai_request.prompt.strip() or "No extra prompt was provided."
    templates = {
        AiToolRequest.ToolType.STUDY_PLAN: (
            "Personal study plan:\n"
            "1. Review the weakest topic first.\n"
            "2. Complete one focused practice quiz.\n"
            "3. Summarize the lesson in your own words.\n\n"
            f"Context: {prompt}"
        ),
        AiToolRequest.ToolType.QUIZ_GENERATOR: (
            "Generated quiz:\n"
            "1. Define the central concept.\n"
            "2. Apply it to a realistic scenario.\n"
            "3. Explain why one incorrect answer is wrong.\n\n"
            f"Source: {prompt}"
        ),
        AiToolRequest.ToolType.LESSON_SUMMARY: (
            "Lesson summary:\n"
            "Key idea, supporting details, and one practice question are ready for review.\n\n"
            f"Material: {prompt}"
        ),
        AiToolRequest.ToolType.FEEDBACK_ASSISTANT: (
            "Feedback draft:\n"
            "Strong effort. Next, improve clarity, evidence, and final reflection.\n\n"
            f"Submission context: {prompt}"
        ),
        AiToolRequest.ToolType.RISK_INSIGHTS: (
            "Learning risk insight:\n"
            "Watch progress, missing work, and assessment trend before escalating.\n\n"
            f"Class context: {prompt}"
        ),
    }
    return templates.get(ai_request.tool_type, f"AI response queued for: {prompt}")
