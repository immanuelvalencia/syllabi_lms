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

import os
import google.generativeai as genai
from pgvector.django import L2Distance
from .models import DocumentChunk

def generate_rag_response(course_id, prompt):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "Error: GEMINI_API_KEY environment variable is not configured."
        
    genai.configure(api_key=api_key)
    
    try:
        result = genai.embed_content(
            model="models/gemini-embedding-2",
            content=prompt,
            task_type="retrieval_query",
        )
        prompt_embedding = result['embedding']
    except Exception as e:
        return f"Error generating embedding for prompt: {str(e)}"
        
    top_chunks = DocumentChunk.objects.filter(
        material__course_id=course_id
    ).annotate(
        distance=L2Distance("embedding", prompt_embedding)
    ).order_by("distance")[:8]
    
    context_text = "\n\n---\n\n".join([chunk.content for chunk in top_chunks])
    
    if not context_text:
        context_text = "No processed course materials found for this course."
        
    system_prompt = (
        "You are an AI teaching assistant for this course. "
        "Use the provided excerpts from the course materials to fulfill the user's request. "
        "If the context does not contain enough information, state that clearly but try your best to be helpful based on general knowledge."
    )
    
    try:
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_prompt
        )
        response = model.generate_content(
            f"Course Materials Context:\n{context_text}\n\nUser Request: {prompt}"
        )
        return response.text
    except Exception as e:
        return f"Error generating response: {str(e)}"
