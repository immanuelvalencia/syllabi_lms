from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .tasks import process_material_rag

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


def _build_course_analytics(course, user, section_ids=None):
    assignments = list(course.assignments.all())
    assignment_count = len(assignments)
    submissions = Submission.objects.select_related("assignment").filter(assignment__course=course)
    submissions_by_student = {}
    for submission in submissions:
        submissions_by_student.setdefault(submission.student_id, []).append(submission)

    ai_section_counts = {}
    section_ai_requests = AiToolRequest.objects.filter(
        user=user,
        metadata__course_public_id=str(course.public_id),
        metadata__section_public_id__isnull=False,
    ).values("metadata__section_public_id").annotate(total=Count("id"))
    for item in section_ai_requests:
        ai_section_counts[item["metadata__section_public_id"]] = item["total"]

    sections = list(course.sections.all())
    if section_ids is not None:
        selected_ids = set(section_ids)
        sections = [section for section in sections if section.id in selected_ids]

    analytics_rows = []
    for section in sections:
        student_ids = [enrollment.student_id for enrollment in section.section_enrollments.all()]
        section_submissions = [
            submission
            for student_id in student_ids
            for submission in submissions_by_student.get(student_id, [])
        ]
        submitted_count = len(section_submissions)
        graded_count = sum(1 for submission in section_submissions if submission.score is not None)
        expected_count = len(student_ids) * assignment_count
        scored_percentages = [
            float(submission.score) / submission.assignment.max_score * 100
            for submission in section_submissions
            if submission.score is not None and submission.assignment.max_score
        ]
        submission_rate = round(submitted_count / expected_count * 100) if expected_count else 0
        grading_rate = round(graded_count / submitted_count * 100) if submitted_count else 0
        average_score = round(sum(scored_percentages) / len(scored_percentages)) if scored_percentages else None
        attention = []
        if not student_ids:
            attention.append("No students enrolled")
        elif expected_count and submission_rate < 70:
            attention.append("Low submission rate")
        if submitted_count > graded_count:
            attention.append(f"{submitted_count - graded_count} ungraded")
        if average_score is not None and average_score < 75:
            attention.append("Score trend below 75%")

        analytics_rows.append({
            "section": section,
            "student_count": len(student_ids),
            "submitted_count": submitted_count,
            "expected_count": expected_count,
            "submission_rate": submission_rate,
            "graded_count": graded_count,
            "grading_rate": grading_rate,
            "average_score": average_score,
            "ai_count": ai_section_counts.get(str(section.public_id), 0),
            "attention": attention,
        })

    sections_with_students = [row for row in analytics_rows if row["student_count"]]
    return {
        "assignment_count": assignment_count,
        "section_count": len(analytics_rows),
        "total_students": sum(row["student_count"] for row in analytics_rows),
        "total_submissions": sum(row["submitted_count"] for row in analytics_rows),
        "needs_attention_count": sum(1 for row in analytics_rows if row["attention"]),
        "top_section": max(
            sections_with_students,
            key=lambda row: (row["submission_rate"], row["average_score"] or 0),
            default=None,
        ),
        "rows": analytics_rows,
    }


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
    course_form = CourseForm(instance=course)
    section_form = CourseSectionForm()
    enrollment_form = SectionEnrollmentForm()
    material_form = CourseMaterialForm()
    manage_course_modal_open = False

    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied

        action = request.POST.get("action")
        if action == "edit_course":
            course_form = CourseForm(request.POST, instance=course)
            if course_form.is_valid():
                course = course_form.save()
                messages.success(request, "Course updated.")
                return redirect(course.get_absolute_url())
            manage_course_modal_open = True
        elif action == "delete_course":
            confirm_code = request.POST.get("confirm_course_code", "")
            if confirm_code != course.code:
                messages.error(request, "Enter the course code exactly to delete this course.")
                manage_course_modal_open = True
            else:
                for material in course.materials.all():
                    if material.file:
                        material.file.delete(save=False)
                course.delete()
                messages.success(request, "Course deleted.")
                return redirect("academics:teacher_courses")
        elif action == "create_section":
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
    course_analytics = _build_course_analytics(course, request.user)
    context = {
        "course": course,
        "profile": profile,
        "can_manage": can_manage,
        "course_analytics": course_analytics,
        "course_form": course_form,
        "section_form": section_form,
        "enrollment_form": enrollment_form,
        "material_form": material_form,
        "manage_course_modal_open": manage_course_modal_open,
        "ai_requests": ai_requests,
    }
    return render(request, "academics/course_detail.html", context)


@login_required
def course_analytics_pdf(request, slug):
    course = get_object_or_404(
        Course.objects.select_related("instructor").prefetch_related(
            "assignments",
            "sections__section_enrollments__student",
        ),
        slug__iexact=slug,
    )
    if not _can_view_course(request.user, course):
        raise PermissionDenied

    section_ids = None
    sections_param = request.GET.get("sections", "")
    if sections_param:
        section_ids = []
        for value in sections_param.split(","):
            try:
                section_ids.append(int(value))
            except ValueError:
                continue

    analytics = _build_course_analytics(course, request.user, section_ids=section_ids)

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=0.45 * inch,
        leftMargin=0.45 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"{course.title} - Course Analytics", styles["Title"]),
        Paragraph(f"Course code: {course.code}", styles["Normal"]),
        Spacer(1, 0.18 * inch),
        Paragraph(
            f"Sections: {analytics['section_count']} | Students: {analytics['total_students']} | "
            f"Assignments: {analytics['assignment_count']} | Needs attention: {analytics['needs_attention_count']}",
            styles["Normal"],
        ),
        Spacer(1, 0.22 * inch),
    ]

    table_data = [[
        "Section",
        "Students",
        "Submissions",
        "Submission %",
        "Grading %",
        "Avg score",
        "AI use",
        "Teacher cue",
    ]]
    for row in analytics["rows"]:
        table_data.append([
            row["section"].name,
            str(row["student_count"]),
            f"{row['submitted_count']}/{row['expected_count']}",
            f"{row['submission_rate']}%",
            f"{row['grading_rate']}%",
            f"{row['average_score']}%" if row["average_score"] is not None else "No scores",
            str(row["ai_count"]),
            ", ".join(row["attention"]) if row["attention"] else "On track",
        ])

    if len(table_data) == 1:
        story.append(Paragraph("No sections selected for this export.", styles["Normal"]))
    else:
        table = Table(
            table_data,
            repeatRows=1,
            colWidths=[1.7 * inch, 0.7 * inch, 1.0 * inch, 1.0 * inch, 0.9 * inch, 0.8 * inch, 0.65 * inch, 2.2 * inch],
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfdf5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#14532d")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(table)

    doc.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{course.slug or course.code}-analytics.pdf"'
    return response


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
def analyze_material(request, material_id):
    if request.method == "POST":
        material = get_object_or_404(CourseMaterial, id=material_id)
        course = material.course
        if not _can_manage_course(request.user, course):
            raise PermissionDenied
            
        from .models import AiToolRequest
        ai_request = AiToolRequest.objects.create(
            user=request.user,
            tool_type=AiToolRequest.ToolType.DOCUMENT_ANALYSIS,
            prompt=f"Extract and index knowledge from document: {material.display_name}",
        )
        from .tasks import process_material_rag
        process_material_rag.delay(material.id, ai_request.id)
        messages.success(request, f"Started analyzing '{material.display_name}'. This may take a moment.")
            
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
    
    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied
        
        action = request.POST.get("action")
        if action == "edit_section":
            section_form = CourseSectionForm(request.POST, instance=section)
            if section_form.is_valid():
                section_form.save()
                messages.success(request, f"Section {section.name} updated.")
                return redirect(section.get_absolute_url())
        elif action == "delete_section":
            confirm_code = request.POST.get("confirm_course_code")
            if confirm_code == course.code:
                section.delete()
                messages.success(request, "Section deleted successfully.")
                return redirect(course.get_absolute_url())
            else:
                messages.error(request, "Course code did not match. Section not deleted.")
                return redirect(section.get_absolute_url())
    else:
        section_form = CourseSectionForm(instance=section)

    student_count = section.section_enrollments.count()
    student_ids = list(section.section_enrollments.values_list("student_id", flat=True))
    course_student_count = Enrollment.objects.filter(course=course).count()
    pending_submissions = Submission.objects.none()
    if can_manage:
        pending_submissions = Submission.objects.filter(
            assignment__course=course,
            student_id__in=student_ids,
            score__isnull=True,
        ).select_related("student", "assignment")[:8]
    section_announcements = Announcement.objects.filter(
        Q(audience_all=True) | Q(course=course)
    ).select_related("author", "course")[:5]
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
        "pending_submissions": pending_submissions,
        "section_announcements": section_announcements,
        "ai_requests": ai_requests,
        "section_form": section_form,
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

import json
from django.http import JsonResponse
from .services import generate_rag_response

@login_required
def ai_generate(request, slug):
    course = get_object_or_404(Course, public_id=slug)
    
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            prompt = data.get("prompt")
            if not prompt:
                return JsonResponse({"error": "Prompt is required"}, status=400)
                
            response_text = generate_rag_response(course.id, prompt)
            return JsonResponse({"response": response_text})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
            
    return JsonResponse({"error": "Invalid method"}, status=405)

@login_required
def ai_tasks_list(request):
    tasks = request.user.ai_tool_requests.all()
    profile = request.user.profile if hasattr(request.user, "profile") else None
    return render(request, "academics/ai_tasks_list.html", {"tasks": tasks, "profile": profile})
