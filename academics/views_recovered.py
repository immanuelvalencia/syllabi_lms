import re

with open("c:/Users/Jim/Development/syllabi_lms/academics/views.py", "r") as f:
    content = f.read()

# We need to replace the ai_resource_assistant function block
old_func = """@login_required
def ai_resource_assistant(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    
    sessions = ResourceAssistantSession.objects.filter(course=course).order_by("-created_at")
    
    if request.method == "POST":
        topic = request.POST.get("topic")
        trusted_sources = request.POST.get("trusted_sources", "")
        free_only = request.POST.get("free_only") == "on"
        
        if free_only and "free" not in topic.lower():
            topic += " (must be free/open source)"
            
        if topic:
            session = ResourceAssistantSession.objects.create(
                course=course,
                author=request.user,
                topic=topic,
                trusted_sources=trusted_sources
            )
            
            # Start background task
            from .tasks import generate_resources_task
            generate_resources_task.delay(session.id)
            
            return redirect("academics:resource_session_detail", slug=slug, session_id=session.id)
            
    return render(request, "academics/ai_resource_assistant.html", {
        "course": course,
        "sessions": sessions,
        "show_form": True
    })"""

new_func = """@login_required
def ai_resource_assistant(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    
    sessions = ResourceAssistantSession.objects.filter(course=course).order_by("-created_at")
    
    if request.method == "POST":
        topic = request.POST.get("topic")
        lesson_plan_id = request.POST.get("based_on_lesson_plan")
        materials_ids = request.POST.getlist("based_on_materials")
        
        if topic:
            session = ResourceAssistantSession.objects.create(
                course=course,
                author=request.user,
                topic=topic,
                based_on_lesson_plan_id=lesson_plan_id if lesson_plan_id else None
            )
            if materials_ids:
                session.based_on_materials.set(materials_ids)
            
            # Start background task
            from .tasks import generate_resources_task
            generate_resources_task.delay(session.id)
            
            return redirect("academics:resource_session_detail", slug=slug, session_id=session.id)
            
    # Load extra context for the form and aggregated views
    approved_resources = SuggestedResource.objects.filter(session__course=course, is_approved=True, is_rejected=False).order_by("-created_at")
    website_filters = CourseWebsiteFilter.objects.filter(course=course)
    resource_tags = ResourceTag.objects.filter(course=course)
    lesson_plans = course.generated_lesson_plans.all()
    materials = course.materials.filter(is_processed=True)
    
    return render(request, "academics/ai_resource_assistant.html", {
        "course": course,
        "sessions": sessions,
        "show_form": True,
        "approved_resources": approved_resources,
        "website_filters": website_filters,
        "resource_tags": resource_tags,
        "lesson_plans": lesson_plans,
        "materials": materials,
    })"""

if old_func in content:
    content = content.replace(old_func, new_func)
    with open("c:/Users/Jim/Development/syllabi_lms/academics/views.py", "w") as f:
        f.write(content)
    print("Replaced successfully")
else:
    print("Could not find old func block exactly")
