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

@shared_task
def process_material_rag(material_id, ai_request_id=None):
    import os
    import tiktoken
    import google.generativeai as genai
    from academics.models import CourseMaterial, DocumentChunk, AiToolRequest
    from PyPDF2 import PdfReader
    from docx import Document
    from django.utils import timezone
    
    ai_request = None
    if ai_request_id:
        try:
            ai_request = AiToolRequest.objects.get(id=ai_request_id)
            ai_request.status = AiToolRequest.Status.RUNNING
            ai_request.started_at = timezone.now()
            ai_request.save(update_fields=['status', 'started_at'])
        except AiToolRequest.DoesNotExist:
            pass

    try:
        material = CourseMaterial.objects.get(id=material_id)
    except CourseMaterial.DoesNotExist:
        if ai_request:
            ai_request.status = AiToolRequest.Status.FAILED
            ai_request.error_message = "Material does not exist"
            ai_request.completed_at = timezone.now()
            ai_request.save(update_fields=['status', 'error_message', 'completed_at'])
        return "Material does not exist"
    
    text = ""
    ext = material.file_extension
    try:
        with material.file.open('rb') as f:
            if ext == ".pdf":
                reader = PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            elif ext in [".doc", ".docx"]:
                doc = Document(f)
                for para in doc.paragraphs:
                    text += para.text + "\n"
            elif ext == ".txt":
                text = f.read().decode('utf-8', errors='ignore')
            else:
                material.is_processed = True
                material.save(update_fields=["is_processed"])
                return "Unsupported format"
    except Exception as e:
        print(f"Error extracting text: {e}")
        if ai_request:
            ai_request.status = AiToolRequest.Status.FAILED
            ai_request.error_message = f"Error extracting text: {e}"
            ai_request.completed_at = timezone.now()
            ai_request.save(update_fields=['status', 'error_message', 'completed_at'])
        return str(e)
        
    if not text.strip():
        material.is_processed = True
        material.save(update_fields=["is_processed"])
        if ai_request:
            ai_request.status = AiToolRequest.Status.FAILED
            ai_request.error_message = "No text could be extracted from the document."
            ai_request.completed_at = timezone.now()
            ai_request.save(update_fields=['status', 'error_message', 'completed_at'])
        return "No text extracted"

    encoder = tiktoken.get_encoding("cl100k_base")
    tokens = encoder.encode(text)
    chunk_size = 500
    overlap = 50
    chunks = []
    
    i = 0
    while i < len(tokens):
        chunk_tokens = tokens[i:i + chunk_size]
        chunks.append(encoder.decode(chunk_tokens))
        i += chunk_size - overlap
        
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Warning: GEMINI_API_KEY not set. Skipping embedding.")
        if ai_request:
            ai_request.status = AiToolRequest.Status.FAILED
            ai_request.error_message = "GEMINI_API_KEY missing"
            ai_request.completed_at = timezone.now()
            ai_request.save(update_fields=['status', 'error_message', 'completed_at'])
        return "GEMINI_API_KEY missing"

    genai.configure(api_key=api_key)
    
    try:
        DocumentChunk.objects.filter(material=material).delete()
        
        batch_size = 100
        for j in range(0, len(chunks), batch_size):
            batch_chunks = chunks[j:j+batch_size]
            
            result = genai.embed_content(
                model="models/gemini-embedding-2",
                content=batch_chunks,
                task_type="retrieval_document"
            )
            
            chunk_objects = []
            for k, embedding in enumerate(result['embedding']):
                chunk_objects.append(
                    DocumentChunk(
                        material=material,
                        content=batch_chunks[k],
                        embedding=embedding,
                        chunk_index=j + k
                    )
                )
            DocumentChunk.objects.bulk_create(chunk_objects)
            
    except Exception as e:
        print(f"Error embedding: {e}")
        if ai_request:
            ai_request.status = AiToolRequest.Status.FAILED
            ai_request.error_message = str(e)
            ai_request.completed_at = timezone.now()
            ai_request.save(update_fields=['status', 'error_message', 'completed_at'])
        return str(e)

    material.is_processed = True
    material.save(update_fields=["is_processed"])
    
    if ai_request:
        ai_request.status = AiToolRequest.Status.COMPLETED
        ai_request.result = f"Successfully analyzed and embedded {len(chunks)} knowledge chunks from {material.display_name}."
        ai_request.completed_at = timezone.now()
        ai_request.save(update_fields=['status', 'result', 'completed_at'])
        
    return f"Processed {len(chunks)} chunks"
