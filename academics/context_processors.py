from .models import Course, Enrollment, Profile


def canvas_navigation(request):
    if not request.user.is_authenticated:
        return {"nav_courses": [], "active_course_code": ""}

    profile, _created = Profile.objects.get_or_create(user=request.user)
    if profile.role == Profile.Role.INSTRUCTOR:
        courses = Course.objects.filter(instructor=request.user).order_by("code")[:12]
    elif profile.role == Profile.Role.STUDENT:
        course_ids = Enrollment.objects.filter(student=request.user).values_list("course_id", flat=True)
        courses = Course.objects.filter(id__in=course_ids).order_by("code")[:12]
    else:
        courses = Course.objects.order_by("code")[:12]

    active_course_code = ""
    if request.resolver_match:
        active_course_code = request.resolver_match.kwargs.get("course_code", "")
    return {"nav_courses": courses, "active_course_code": active_course_code.lower()}
