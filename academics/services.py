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
        chunks = DocumentChunk.objects.filter(material_id__in=materials_ids).order_by("material_id", "chunk_index")
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


def generate_submission_analysis(submission, answers_breakdown, student_notes=""):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "Error: GEMINI_API_KEY environment variable is not configured."
        
    client = genai.Client(api_key=api_key)
    
    assignment = submission.assignment
    student = submission.student
    
    system_prompt = (
        "You are an expert academic evaluator and teaching assistant. "
        "Your task is to analyze a student's submission to a quiz or assignment. "
        "Identify what items/questions they got correct vs incorrect. "
        "Provide detailed pedagogical insights, highlighting their strengths, weaknesses, "
        "and suggestions for improvement. "
        "IMPORTANT: You must return the output STRICTLY in Markdown format, with clear headings, "
        "bullet points, and premium styling formatting. Do not wrap the output in markdown code blocks. "
        "CRITICAL: Do NOT use any emojis, emoji symbols, or icons anywhere in your generated report."
    )
    
    breakdown_text = []
    for i, ans in enumerate(answers_breakdown, 1):
        status = "Correct" if ans["is_correct"] else "Incorrect"
        points_info = f"{ans['points']} pts"
        q_text = f"Question {i}: {ans['question_text']}\n"
        q_text += f"Student's Answer: {ans['student_answer'] or '(No Answer)'}\n"
        q_text += f"Correct Answer: {ans['correct_answer'] or '(Open Ended/Manual)'}\n"
        q_text += f"Result: {status} ({points_info})\n"
        breakdown_text.append(q_text)
        
    breakdown_formatted = "\n---\n".join(breakdown_text)
    
    prompt = f"""
Assignment Title: {assignment.title}
Max Score: {assignment.max_score}
Student Name: {student.get_full_name() or student.username}
Student Notes/Comments: {student_notes or '(None)'}

Student Submission Answers Breakdown:
{breakdown_formatted}

Please analyze this student's work.
In your analysis, include:
1. Performance Summary (overall score vs max score context).
2. Strengths (what concepts did they demonstrate mastery of?).
3. Weaknesses (what concepts did they struggle with or get wrong?).
4. Recommendations & Study Suggestions (specific topics, actions, or focus areas to improve their understanding).
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_prompt)
        )
        return response.text
    except Exception as e:
        return f"Error generating submission analysis: {str(e)}"


def generate_performance_insights(course, section, stats_summary):
    """
    Generate a GenAI-powered narrative performance insights report
    for a course section, based on pre-computed analytics data.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "Error: GEMINI_API_KEY environment variable is not configured."

    client = genai.Client(api_key=api_key)

    system_prompt = (
        "You are an expert academic analytics advisor for university instructors. "
        "Your task is to analyze class performance data and produce a clear, actionable insights report. "
        "IMPORTANT: You must return the output STRICTLY in Markdown format with clear headings and bullet points. "
        "Do NOT wrap the output in markdown code blocks. "
        "CRITICAL: Do NOT use any emojis, emoji symbols, unicode icons, or decorative characters anywhere in your report. "
        "Use only plain text with standard markdown formatting."
    )

    prompt = f"""
Course: {course.title} ({course.code})
Section: {section.name}
Schedule: {section.schedule_title or 'Not set'} | {section.meeting_days or 'Not set'}

CLASS PERFORMANCE DATA:
- Total Students: {stats_summary['student_count']}
- Total Activities: {stats_summary['assignment_count']}
- Class Average: {stats_summary['class_average']}%
- Class Median: {stats_summary['class_median']}%
- Highest Score: {stats_summary['class_highest']}%
- Lowest Score: {stats_summary['class_lowest']}%
- Submission Rate: {stats_summary['submission_rate']}%
- Grading Completion: {stats_summary['grading_completion']}%

PERFORMANCE TIERS:
- Excellent (>=90%): {stats_summary['performance_tiers'][0]} students
- Good (>=75%): {stats_summary['performance_tiers'][1]} students
- Needs Improvement (>=60%): {stats_summary['performance_tiers'][2]} students
- At Risk (<60%): {stats_summary['performance_tiers'][3]} students

SCORE DISTRIBUTION (0-10%, 10-20%, ... 90-100%):
{stats_summary['score_distribution']}

PER-ACTIVITY CLASS AVERAGES:
{stats_summary['activity_data']}

TOP STRUGGLING QUESTIONS (lowest correct rates):
{stats_summary['struggling_questions']}

Please produce a detailed performance insights report that includes:
1. Executive Summary - overall class health in 2-3 sentences.
2. Key Findings - notable patterns, strengths, and concerns with specific data references.
3. At-Risk Student Analysis - discuss the proportion and severity of struggling students.
4. Question-Level Insights - analyze which topics/concepts students find most difficult based on the struggling questions.
5. Actionable Recommendations - specific, practical steps the instructor can take to improve outcomes (e.g., review sessions, targeted practice, re-teaching specific topics).
6. Submission & Grading Notes - observations about submission rates and grading completion.
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        return response.text
    except Exception as e:
        return f"Error generating performance insights: {str(e)}"

