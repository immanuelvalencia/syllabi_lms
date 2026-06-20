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
def generate_lesson_plan_task(plan_id, materials_ids, topic, modules, duration, instructions):
    from academics.models import GeneratedLessonPlan
    from django.utils import timezone
    try:
        plan = GeneratedLessonPlan.objects.get(id=plan_id)
        plan.status = GeneratedLessonPlan.Status.RUNNING
        plan.save(update_fields=["status"])
        
        from academics.services import generate_lesson_plan_content
        content = generate_lesson_plan_content(
            course=plan.course,
            materials_ids=materials_ids,
            topic=topic,
            modules=modules,
            duration=duration,
            instructions=instructions
        )
        
        if not plan.title:
            title = topic if topic else f"Lesson Plan - {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            plan.title = title
            
        plan.content = content
        plan.status = GeneratedLessonPlan.Status.COMPLETED
        plan.save(update_fields=["title", "content", "status"])
        return content
    except Exception as e:
        try:
            plan = GeneratedLessonPlan.objects.get(id=plan_id)
            plan.status = GeneratedLessonPlan.Status.FAILED
            plan.error_message = str(e)
            plan.save(update_fields=["status", "error_message"])
        except Exception:
            pass
        raise e

@shared_task
def process_material_rag(material_id, ai_request_id=None):
    import os
    import tiktoken
    from google import genai
    from google.genai import types
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

    client = genai.Client(api_key=api_key)
    
    try:
        DocumentChunk.objects.filter(material=material).delete()
        
        chunk_objects = []
        for j, chunk_text in enumerate(chunks):
            result = client.models.embed_content(
                model="gemini-embedding-2",
                contents=chunk_text,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
            )
            
            chunk_objects.append(
                DocumentChunk(
                    material=material,
                    content=chunk_text,
                    embedding=result.embeddings[0].values,
                    chunk_index=j
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

import json
import re
import requests
from bs4 import BeautifulSoup
from django.utils import timezone

def extract_thumbnail_from_url(url):
    try:
        # YouTube specific fast extraction
        if "youtube.com/watch" in url:
            video_id_match = re.search(r"v=([a-zA-Z0-9_-]+)", url)
            if video_id_match:
                return f"https://img.youtube.com/vi/{video_id_match.group(1)}/hqdefault.jpg"
        
        # OpenGraph fallback
        response = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                return og_image["content"]
    except Exception as e:
        print(f"Error fetching thumbnail for {url}: {e}")
    return None

@shared_task
def generate_resources_task(session_id, include_videos=True, include_books=True):
    from academics.models import ResourceAssistantSession, SuggestedResource, ResourceTag
    import os
    import json
    from ddgs import DDGS
    from google import genai
    from google.genai import types
    
    try:
        session = ResourceAssistantSession.objects.get(id=session_id)
        session.status = ResourceAssistantSession.Status.RUNNING
        session.save(update_fields=["status"])
        
        topic = session.topic
        
        # 1. Gather Filters
        filters = session.course.website_filters.all()
        trusted = [f.url for f in filters if f.filter_type == 'trusted']
        excluded = [f.url for f in filters if f.filter_type == 'excluded']
        
        trusted_query = " OR ".join([f"site:{d}" for d in trusted]) if trusted else ""
        excluded_query = " ".join([f"-site:{d}" for d in excluded]) if excluded else ""
        
        query_modifier = ""
        if trusted_query:
            query_modifier += f" ({trusted_query})"
        if excluded_query:
            query_modifier += f" {excluded_query}"
            
        # 2. Gather Context
        context_parts = []
        if session.based_on_lesson_plan:
            context_parts.append(f"LESSON PLAN CONTENT:\\n{session.based_on_lesson_plan.content}\\n")
        
        for mat in session.based_on_materials.all():
            chunks = mat.chunks.order_by('chunk_index')[:5] # limit context size
            text = "\\n".join([c.content for c in chunks])
            context_parts.append(f"MATERIAL ({mat.title}):\\n{text}\\n")
            
        context_str = "\\n".join(context_parts)
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is missing")
            
        client = genai.Client(api_key=api_key)
        
        # 3. Generate better search queries based on context
        search_queries = []
        if context_str:
            prompt_queries = f"""
            I need to find free resources for the topic: {topic}.
            
            Here is the context (Lesson Plan / Course Materials) for this topic:
            {context_str}
            
            Based on the context, provide 4 highly specific search queries that would be typed into a search engine.
"""
            if include_videos and include_books:
                prompt_queries += "\n- 2 queries to find lecture videos.\n- 2 queries to find free textbooks or readings."
            elif include_videos:
                prompt_queries += "\n- 4 queries to find lecture videos."
            elif include_books:
                prompt_queries += "\n- 4 queries to find free textbooks or readings."
            else:
                prompt_queries += "\n- 4 queries to find lecture videos.\n- 4 queries to find free textbooks or readings."
                
            prompt_queries += """
            Make the queries concise (under 8 words). Do NOT include site: operators.
            
            Respond ONLY with a JSON array of strings.
            """
            try:
                q_resp = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt_queries,
                    config=types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json")
                )
                try:
                    search_queries = json.loads(q_resp.text)
                except json.JSONDecodeError:
                    cleaned = q_resp.text.strip()
                    if cleaned.startswith("```json"): cleaned = cleaned[7:]
                    if cleaned.endswith("```"): cleaned = cleaned[:-3]
                    search_queries = json.loads(cleaned)
            except Exception as e:
                print(f"Error generating queries from context: {e}")
                
        if not search_queries:
            search_queries = [
                f"lecture video {topic}",
                f"free textbook or reading {topic}"
            ]
            
        # 4. Search DDGS
        candidate_items = []
        for q in search_queries:
            full_query = f"{q}{query_modifier}"
            try:
                results = DDGS().text(full_query, max_results=5)
                for res in results:
                    candidate_items.append({
                        "title": res.get("title", ""),
                        "url": res.get("href", ""),
                        "resource_type": "video" if "video" in q.lower() else "book",
                        "description": res.get("body", "")
                    })
            except Exception as e:
                print(f"Error DDGS query '{full_query}': {e}")
                
        # Deduplicate candidates
        seen_urls = set()
        unique_candidates = []
        for item in candidate_items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                unique_candidates.append(item)
                
        # 5. Gather existing tags
        existing_tags = list(session.course.resource_tags.values_list('name', flat=True))
        
        # 6. Gemini Final Evaluation
        prompt = f"""
        You are an academic resource curator.
        I have scraped {len(unique_candidates)} candidate web links.
        
        COURSE CONTEXT (Use this to judge relevance):
        {context_str if context_str else "No specific context provided, rely on the topic alone."}
        
        CANDIDATE LINKS:
        {json.dumps(unique_candidates, indent=2)}
        
        TASK:
        1. Select the top most relevant results from the candidates. Select up to 5 videos and 5 books/readings if both are requested.
        2. Improve their descriptions to be concise (1-2 sentences) and highlight why it's useful.
        3. Assign up to 3 relevant tags to each resource. You may choose from existing tags: {existing_tags}. If none fit perfectly, you can invent new short tags.
        
        Respond ONLY with a JSON array of objects.
        Each object must have:
        - "title": (string)
        - "url": (string)
        - "resource_type": (string) "book" or "video"
        - "description": (string)
        - "tags": (array of strings)
        """
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json"
            )
        )
        
        try:
            final_items = json.loads(response.text)
        except json.JSONDecodeError:
            cleaned = response.text.strip()
            if cleaned.startswith("```json"): cleaned = cleaned[7:]
            if cleaned.endswith("```"): cleaned = cleaned[:-3]
            final_items = json.loads(cleaned)
            
        # 7. Save Resources
        from academics.tasks import extract_thumbnail_from_url
        for item in final_items:
            url = item.get("url", "")
            if not url: continue
            
            rtype = item.get("resource_type", "book").lower()
            if rtype not in ["book", "video"]: rtype = "book"
            
            res_obj = SuggestedResource.objects.create(
                session=session,
                title=item.get("title", "Untitled")[:300],
                url=url[:500],
                resource_type=rtype,
                thumbnail_url=extract_thumbnail_from_url(url)[:500] if extract_thumbnail_from_url(url) else None,
                description=item.get("description", "")
            )
            
            # Handle tags
            tags_list = item.get("tags", [])
            for t in tags_list:
                tag_name = str(t).strip()[:50]
                if tag_name:
                    tag_obj, _ = ResourceTag.objects.get_or_create(course=session.course, name=tag_name)
                    res_obj.tags.add(tag_obj)
                    
        session.status = ResourceAssistantSession.Status.COMPLETED
        session.save(update_fields=["status", "updated_at"])
        
    except Exception as e:
        try:
            session = ResourceAssistantSession.objects.get(id=session_id)
            session.status = ResourceAssistantSession.Status.FAILED
            session.error_message = str(e)
            session.save(update_fields=["status", "error_message", "updated_at"])
        except Exception:
            pass
        raise e
