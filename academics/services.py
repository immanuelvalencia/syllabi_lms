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
from google import genai
from google.genai import types
from pgvector.django import L2Distance
from .models import DocumentChunk

def generate_rag_response(course_id, prompt):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "Error: GEMINI_API_KEY environment variable is not configured."
        
    client = genai.Client(api_key=api_key)
    
    try:
        result = client.models.embed_content(
            model="gemini-embedding-2",
            contents=prompt,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
        )
        prompt_embedding = result.embeddings[0].values
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
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Course Materials Context:\n{context_text}\n\nUser Request: {prompt}",
            config=types.GenerateContentConfig(system_instruction=system_prompt)
        )
        return response.text
    except Exception as e:
        return f"Error generating response: {str(e)}"

def generate_lesson_plan_content(course, materials_ids, topic, modules, duration, instructions):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "Error: GEMINI_API_KEY environment variable is not configured."
        
    client = genai.Client(api_key=api_key)
    
    # If materials are selected, fetch their chunks
    context_text = ""
    if materials_ids:
        chunks = DocumentChunk.objects.filter(material_id__in=materials_ids)
        # We can just join them up, or if there's too many, limit them.
        # Since it's for lesson planning, we might want the whole content or a substantial amount.
        # For simplicity, we just concatenate all chunks of the selected materials.
        context_text = "\n\n---\n\n".join([chunk.content for chunk in chunks])
    
    if not context_text:
        context_text = "No specific course materials provided for context."
        
    system_prompt = (
        "You are an expert curriculum designer and teaching assistant. "
        "Your task is to create a detailed, engaging, and structured lesson plan based on the user's inputs. "
        "IMPORTANT: You must return the output STRICTLY in Markdown format, with appropriate headings, bullet points, and formatting."
    )
    
    prompt = f"""
Course: {course.title}
Course Description: {course.description}
Topic / Focus Area: {topic}
Number of Modules/Sections: {modules}
Estimated Duration: {duration} minutes
Additional Instructions: {instructions}

Course Materials Context:
{context_text}

Please generate the lesson plan now.
"""
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_prompt)
        )
        return response.text
    except Exception as e:
        return f"Error generating lesson plan: {str(e)}"
