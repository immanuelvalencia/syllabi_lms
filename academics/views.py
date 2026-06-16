from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import CourseForm, CourseSectionForm, SectionEnrollmentForm, CourseMaterialForm
from .models import (
    AiToolRequest,
    Announcement,
    Assignment,
    Course,
    CourseMaterial,
    CourseSection,
    Enrollment,
    Profile,
    SectionEnrollment,
    Submission,
)


def _profile_for(user):
    profile, _created = Profile.objects.get_or_create(user=user)
    return profile


def _can_manage_course(user, course):
    profile = _profile_for(user)
    return course.instructor_id == user.id or profile.role in {
        Profile.Role.ACADEMIC_ADMIN,
        Profile.Role.PLATFORM_ADMIN,
    }


def _can_view_course(user, course):
    if _can_manage_course(user, course):
        return True
    return Enrollment.objects.filter(student=user, course=course).exists()


@login_required
def dashboard(request):
    profile = _profile_for(request.user)
    if profile.role == Profile.Role.INSTRUCTOR:
        return redirect("academics:instructor_dashboard")
    if profile.role in {Profile.Role.ACADEMIC_ADMIN, Profile.Role.PLATFORM_ADMIN}:
        return redirect("academics:academic_admin_dashboard")
    return redirect("academics:student_dashboard")


@login_required
def student_dashboard(request):
    enrollments = (
        Enrollment.objects.filter(student=request.user)
        .select_related("course", "course__instructor", "current_lesson")
        .prefetch_related("course__assignments")
    )
    course_ids = enrollments.values_list("course_id", flat=True)
    upcoming_assignments = Assignment.objects.filter(
        course_id__in=course_ids,
        due_at__gte=timezone.now(),
    ).exclude(submissions__student=request.user)[:6]
    announcements = Announcement.objects.filter(
        Q(audience_all=True) | Q(course_id__in=course_ids)
    ).select_related("author", "course")[:5]
    ai_requests = AiToolRequest.objects.filter(user=request.user)[:5]
    average_progress = round(enrollments.aggregate(avg=Avg("progress_percent"))["avg"] or 0)

    context = {
        "profile": _profile_for(request.user),
        "enrollments": enrollments,
        "enrollment_count": enrollments.count(),
        "upcoming_assignments": upcoming_assignments,
        "upcoming_assignment_count": upcoming_assignments.count(),
        "announcements": announcements,
        "ai_requests": ai_requests,
        "average_progress": average_progress,
        "average_progress_label": f"{average_progress}%",
    }
    return render(request, "academics/dashboards/student.html", context)


@login_required
def instructor_dashboard(request):
    courses = Course.objects.filter(instructor=request.user).prefetch_related("enrollments", "assignments")
    course_ids = courses.values_list("id", flat=True)
    pending_submissions = Submission.objects.filter(
        assignment__course_id__in=course_ids,
        score__isnull=True,
    ).select_related("student", "assignment", "assignment__course")[:8]
    at_risk_count = Enrollment.objects.filter(course_id__in=course_ids, progress_percent__lt=45).count()

    context = {
        "profile": _profile_for(request.user),
        "courses": courses,
        "course_count": courses.count(),
        "pending_submissions": pending_submissions,
        "pending_submission_count": pending_submissions.count(),
        "at_risk_count": at_risk_count,
        "student_count": Enrollment.objects.filter(course_id__in=course_ids).count(),
        "assignment_count": Assignment.objects.filter(course_id__in=course_ids).count(),
    }
    return render(request, "academics/dashboards/instructor.html", context)


@login_required
def teacher_courses(request):
    profile = _profile_for(request.user)
    if profile.role != Profile.Role.INSTRUCTOR:
        raise PermissionDenied

    courses = Course.objects.filter(instructor=request.user).annotate(
        section_count=Count("sections", distinct=True),
        student_total=Count("enrollments", distinct=True),
    )
    return render(
        request,
        "academics/teacher/course_list.html",
        {"profile": profile, "courses": courses},
    )


@login_required
def create_teacher_course(request):
    profile = _profile_for(request.user)
    if profile.role != Profile.Role.INSTRUCTOR:
        raise PermissionDenied

    if request.method == "POST":
        form = CourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.instructor = request.user
            course.department = profile.department
            course.save()
            messages.success(request, "Course created. Add sections, schedule, and students next.")
            return redirect(course.get_absolute_url())
    else:
        form = CourseForm()

    return render(
        request,
        "academics/teacher/course_form.html",
        {"profile": profile, "form": form},
    )


@login_required
def academic_admin_dashboard(request):
    profile = _profile_for(request.user)
    if profile.role not in {Profile.Role.ACADEMIC_ADMIN, Profile.Role.PLATFORM_ADMIN}:
        messages.error(request, "This dashboard is limited to academic administrators.")
        return redirect("academics:dashboard")

    enrollments = Enrollment.objects.select_related("course", "student")
    courses = Course.objects.select_related("instructor")
    ai_requests = AiToolRequest.objects.select_related("user")[:8]

    context = {
        "profile": profile,
        "total_students": Profile.objects.filter(role=Profile.Role.STUDENT).count(),
        "total_instructors": Profile.objects.filter(role=Profile.Role.INSTRUCTOR).count(),
        "total_courses": courses.count(),
        "at_risk_count": enrollments.filter(progress_percent__lt=45).count(),
        "course_activity": courses.annotate(
            student_total=Count("enrollments", distinct=True),
            assignment_total=Count("assignments", distinct=True),
        )[:8],
        "ai_requests": ai_requests,
    }
    return render(request, "academics/dashboards/academic_admin.html", context)


@login_required
def course_detail(request, slug):
    course = get_object_or_404(
        Course.objects.select_related("instructor").prefetch_related(
            "lessons",
            "assignments",
            "sections__section_enrollments__student",
            "materials",
        ),
        slug__iexact=slug,
    )
    if not _can_view_course(request.user, course):
        raise PermissionDenied

    profile = _profile_for(request.user)
    can_manage = _can_manage_course(request.user, course)
    section_form = CourseSectionForm()
    enrollment_form = SectionEnrollmentForm()
    material_form = CourseMaterialForm()

    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied

        action = request.POST.get("action")
        if action == "create_section":
            section_form = CourseSectionForm(request.POST)
            if section_form.is_valid():
                section = section_form.save(commit=False)
                section.course = course
                section.order = course.sections.count() + 1
                section.save()
                messages.success(request, f"Section {section.name} created.")
                return redirect(course.get_absolute_url())
        elif action == "enroll_student":
            section = get_object_or_404(CourseSection, public_id=request.POST.get("section_id"), course=course)
            enrollment_form = SectionEnrollmentForm(request.POST)
            if enrollment_form.is_valid():
                student = enrollment_form.cleaned_data["student"]
                SectionEnrollment.objects.get_or_create(section=section, student=student)
                Enrollment.objects.get_or_create(student=student, course=course)
                messages.success(request, f"{student.get_full_name() or student.username} enrolled in {section.name}.")
                return redirect(course.get_absolute_url())
        elif action == "upload_material":
            material_form = CourseMaterialForm(request.POST, request.FILES)
            if material_form.is_valid():
                material = material_form.save(commit=False)
                material.course = course
                material.save()
                messages.success(request, "Material uploaded.")
                return redirect(course.get_absolute_url())

    ai_requests = AiToolRequest.objects.filter(
        user=request.user,
        metadata__course_public_id=str(course.public_id),
    )[:5]
    context = {
        "course": course,
        "profile": profile,
        "can_manage": can_manage,
        "section_form": section_form,
        "enrollment_form": enrollment_form,
        "material_form": material_form,
        "ai_requests": ai_requests,
    }
    return render(request, "academics/course_detail.html", context)

@login_required
def delete_course_material(request, material_id):
    if request.method == "POST":
        material = get_object_or_404(CourseMaterial, id=material_id)
        course = material.course
        if not _can_manage_course(request.user, course):
            raise PermissionDenied
        
        # Optionally delete the actual file
        if material.file:
            material.file.delete(save=False)
        material.delete()
        
        messages.success(request, "Material deleted.")
        return redirect(course.get_absolute_url())
    return redirect("academics:dashboard")


@login_required
def section_detail(request, slug, section_id):
    course = get_object_or_404(
        Course.objects.select_related("instructor").prefetch_related("sections"),
        slug__iexact=slug,
    )
    if not _can_view_course(request.user, course):
        raise PermissionDenied

    section = get_object_or_404(
        CourseSection.objects.select_related("course").prefetch_related("section_enrollments__student"),
        id=section_id,
        course=course,
    )
    profile = _profile_for(request.user)
    can_manage = _can_manage_course(request.user, course)
    student_count = section.section_enrollments.count()
    course_student_count = Enrollment.objects.filter(course=course).count()
    ai_requests = AiToolRequest.objects.filter(
        user=request.user,
        metadata__course_public_id=str(course.public_id),
        metadata__section_public_id=str(section.public_id),
    )[:5]
    completion_score = min(100, max(0, student_count * 12))

    context = {
        "profile": profile,
        "course": course,
        "section": section,
        "can_manage": can_manage,
        "student_count": student_count,
        "course_student_count": course_student_count,
        "completion_score": completion_score,
        "ai_requests": ai_requests,
    }
    return render(request, "academics/section_detail.html", context)


@login_required
def create_ai_tool_request(request):
    if request.method != "POST":
        return redirect("academics:dashboard")

    tool_type = request.POST.get("tool_type", AiToolRequest.ToolType.STUDY_PLAN)
    prompt = request.POST.get("prompt", "")
    course_public_id = request.POST.get("course_public_id", "")
    section_public_id = request.POST.get("section_public_id", "")
    redirect_to = request.POST.get("next") or "academics:dashboard"
    if tool_type not in AiToolRequest.ToolType.values:
        messages.error(request, "That AI tool is not available.")
        return redirect(redirect_to)

    metadata = {}
    if course_public_id:
        course = get_object_or_404(Course, public_id=course_public_id)
        if not _can_view_course(request.user, course):
            raise PermissionDenied
        metadata["course_public_id"] = str(course.public_id)
        if section_public_id:
            section = get_object_or_404(CourseSection, public_id=section_public_id, course=course)
            metadata["section_public_id"] = str(section.public_id)

    ai_request = AiToolRequest.objects.create(
        user=request.user,
        tool_type=tool_type,
        prompt=prompt,
        metadata=metadata,
    )

    def enqueue_task():
        from .services import enqueue_ai_tool_request

        enqueue_ai_tool_request(ai_request.pk)

    try:
        transaction.on_commit(enqueue_task)
        messages.success(request, "AI request queued. The worker will process it in the background.")
    except Exception as exc:
        ai_request.status = AiToolRequest.Status.FAILED
        ai_request.error_message = str(exc)
        ai_request.completed_at = timezone.now()
        ai_request.save(update_fields=["status", "error_message", "completed_at"])
        messages.error(request, "The AI worker is not available yet.")

    return redirect(redirect_to)
