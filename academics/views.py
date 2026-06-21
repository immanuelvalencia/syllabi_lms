from datetime import timedelta
from io import BytesIO
import json
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Avg, Count, Max, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .tasks import process_material_rag

from .forms import ActivitySectionForm, AssignmentForm, CourseForm, CourseSectionForm, SectionEnrollmentForm, CourseMaterialForm
from .models import (
    ActivitySection,
    AiToolRequest,
    Announcement,
    Assignment,
    Course,
    CourseMaterial,
    CourseSection,
    Enrollment,
    GeneratedLessonPlan,
    Profile,
    Question,
    SectionEnrollment,
    Submission,
    ResourceAssistantSession,
    SuggestedResource,
    GeneratedActivitySheet,
)


def _profile_for(user):
    profile, _created = Profile.objects.get_or_create(user=user)
    return profile


def _can_manage_course(user, course):
    profile = _profile_for(user)
    if profile.role == Profile.Role.PLATFORM_ADMIN:
        return True
    if profile.role == Profile.Role.ACADEMIC_ADMIN and course.school_id == profile.school_id:
        return True
    return course.instructor_id == user.id


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
    if profile.role == Profile.Role.PLATFORM_ADMIN:
        return redirect("academics:platform_admin_dashboard")
    if profile.role == Profile.Role.ACADEMIC_ADMIN:
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
            course.school = profile.school
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

    school = profile.school
    enrollments = Enrollment.objects.filter(course__school=school).select_related("course", "student")
    courses = Course.objects.filter(school=school).select_related("instructor")
    ai_requests = AiToolRequest.objects.select_related("user")[:8]

    context = {
        "profile": profile,
        "total_students": Profile.objects.filter(role=Profile.Role.STUDENT, school=school).count(),
        "total_instructors": Profile.objects.filter(role=Profile.Role.INSTRUCTOR, school=school).count(),
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
    enrollment_form = SectionEnrollmentForm(course=course)
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
            enrollment_form = SectionEnrollmentForm(request.POST, course=course, section=section)
            if enrollment_form.is_valid():
                student = enrollment_form.cleaned_data["student"]
                SectionEnrollment.objects.filter(section__course=course, student=student).delete()
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

    if can_manage:
        sections = course.sections.all()
    else:
        sections = [
            section for section in course.sections.all()
            if any(se.student_id == request.user.id for se in section.section_enrollments.all())
        ]

    ai_requests = AiToolRequest.objects.filter(
        user=request.user,
        metadata__course_public_id=str(course.public_id),
    )[:5]
    course_analytics = _build_course_analytics(course, request.user)
    context = {
        "course": course,
        "sections": sections,
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
    if not _can_manage_course(request.user, course):
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
    course, section, profile, can_manage = _section_access_context(request.user, slug, section_id)
    section_form = CourseSectionForm(instance=section)
    
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
            messages.error(request, "Course code did not match. Section not deleted.")
            return redirect(section.get_absolute_url())

    context = _section_dashboard_context(course, section, can_manage)
    context.update({
        "profile": profile,
        "course": course,
        "section": section,
        "can_manage": can_manage,
        "section_form": section_form,
    })
    return render(request, "academics/section_detail.html", context)


def _section_access_context(user, slug, section_id):
    course = get_object_or_404(
        Course.objects.select_related("instructor").prefetch_related("sections"),
        slug__iexact=slug,
    )
    if not _can_view_course(user, course):
        raise PermissionDenied

    section = get_object_or_404(
        CourseSection.objects.select_related("course").prefetch_related("section_enrollments__student__profile"),
        id=section_id,
        course=course,
    )
    can_manage = _can_manage_course(user, course)
    if not can_manage:
        is_enrolled = any(se.student_id == user.id for se in section.section_enrollments.all())
        if not is_enrolled:
            raise PermissionDenied
    return course, section, _profile_for(user), can_manage


def _section_dashboard_context(course, section, can_manage):
    section_enrollments = list(
        SectionEnrollment.objects.filter(section=section)
        .select_related("student", "student__profile")
        .order_by("student__last_name", "student__first_name", "student__username")
    )
    student_count = len(section_enrollments)
    student_ids = [enrollment.student_id for enrollment in section_enrollments]
    course_student_count = Enrollment.objects.filter(course=course).count()
    assignments = list(
        course.assignments.filter(Q(course_section=section) | Q(course_section__isnull=True))
        .prefetch_related("submissions")
        .order_by("activity_section__order", "course_section__order", "order", "due_at", "title")
    )
    assignment_count = len(assignments)
    activity_rows = []
    section_student_ids = set(student_ids)
    for assignment in assignments:
        section_submissions = [
            submission
            for submission in assignment.submissions.all()
            if submission.student_id in section_student_ids
        ]
        submitted_count = len(section_submissions)
        ungraded_count = sum(1 for submission in section_submissions if submission.score is None)
        activity_rows.append({
            "assignment": assignment,
            "submitted_count": submitted_count,
            "ungraded_count": ungraded_count,
            "expected_count": student_count,
        })
    pending_submissions = Submission.objects.none()
    if can_manage:
        pending_submissions = Submission.objects.filter(
            Q(assignment__course_section=section) | Q(assignment__course_section__isnull=True),
            assignment__course=course,
            student_id__in=student_ids,
            score__isnull=True,
        ).select_related("student", "assignment")[:8]
    pending_submission_count = Submission.objects.filter(
        Q(assignment__course_section=section) | Q(assignment__course_section__isnull=True),
        assignment__course=course,
        student_id__in=student_ids,
        score__isnull=True,
    ).count()
    total_submission_count = Submission.objects.filter(
        Q(assignment__course_section=section) | Q(assignment__course_section__isnull=True),
        assignment__course=course,
        student_id__in=student_ids,
    ).count()
    due_soon_count = Assignment.objects.filter(
        Q(course_section=section) | Q(course_section__isnull=True),
        course=course,
        due_at__gte=timezone.now(),
        due_at__lte=timezone.now() + timedelta(days=7),
    ).count()
    
    at_risk_count = 0
    if can_manage and student_ids:
        graded_submissions = Submission.objects.filter(
            assignment__course=course,
            student_id__in=student_ids,
            score__isnull=False
        ).select_related('assignment')
        
        student_scores = {}
        for sub in graded_submissions:
            max_score = sub.assignment.max_score or 0
            if max_score > 0:
                if sub.student_id not in student_scores:
                    student_scores[sub.student_id] = {'earned': 0, 'total': 0}
                student_scores[sub.student_id]['earned'] += sub.score
                student_scores[sub.student_id]['total'] += max_score
                
        for sid, scores in student_scores.items():
            if scores['total'] > 0 and (scores['earned'] / scores['total']) < 0.70:
                at_risk_count += 1

    section_alerts = []
    if student_count == 0:
        section_alerts.append({
            "level": "warning",
            "title": "No students enrolled",
            "body": "Add students to this section before assigning graded work.",
            "icon": "bi-people",
        })
    if pending_submission_count:
        section_alerts.append({
            "level": "danger",
            "title": f"{pending_submission_count} item{'s' if pending_submission_count != 1 else ''} to grade",
            "body": "Review submitted work so students can see feedback and scores.",
            "icon": "bi-clipboard-check",
        })
    if not section.meeting_days or not section.start_time or not section.end_time:
        section_alerts.append({
            "level": "info",
            "title": "Schedule incomplete",
            "body": "Add meeting days and times to keep this section easy to scan.",
            "icon": "bi-calendar3",
        })
    if not section.location:
        section_alerts.append({
            "level": "info",
            "title": "Location not set",
            "body": "Add a room, online link, or meeting location for this section.",
            "icon": "bi-geo-alt",
        })
    if due_soon_count:
        section_alerts.append({
            "level": "success",
            "title": f"{due_soon_count} upcoming due date{'s' if due_soon_count != 1 else ''}",
            "body": "There is student work due within the next seven days.",
            "icon": "bi-clock",
        })
    completion_score = min(100, max(0, student_count * 12))

    return {
        "student_count": student_count,
        "section_enrollments": section_enrollments,
        "course_student_count": course_student_count,
        "completion_score": completion_score,
        "assignments": assignments,
        "activity_rows": activity_rows,
        "assignment_count": assignment_count,
        "pending_submissions": pending_submissions,
        "pending_submission_count": pending_submission_count,
        "total_submission_count": total_submission_count,
        "due_soon_count": due_soon_count,
        "at_risk_count": at_risk_count,
        "section_alerts": section_alerts,
    }


def _eligible_students_for_course(course):
    instructor_profile = Profile.objects.filter(user=course.instructor).first()
    grade_match = re.search(r"\d+", course.grade_level or "")
    if not instructor_profile or not instructor_profile.school_id or not grade_match:
        return get_user_model().objects.none()

    return get_user_model().objects.filter(
        profile__role=Profile.Role.STUDENT,
        profile__school_id=instructor_profile.school_id,
        profile__grade_level=int(grade_match.group()),
        is_active=True,
    ).select_related("profile").order_by("last_name", "first_name", "username")


def _next_assignment_order(course, activity_section):
    return (
        Assignment.objects.filter(course=course, activity_section=activity_section).aggregate(max_order=Max("order"))["max_order"]
        or 0
    ) + 1


def _activity_board_context(course):
    activity_sections = list(
        course.activity_sections.prefetch_related("assignments__submissions")
        .order_by("order", "name")
    )
    activity_section_cards = []
    for activity_section in activity_sections:
        section_assignments = list(
            Assignment.objects.filter(course=course, activity_section=activity_section)
            .select_related("course_section")
            .annotate(submission_count=Count("submissions", distinct=True))
            .order_by("course_section__order", "order", "due_at", "title")
        )
        activity_section_cards.append({
            "activity_section": activity_section,
            "assignments": section_assignments,
        })

    other_assignments = list(
        Assignment.objects.filter(course=course, activity_section__isnull=True)
        .select_related("course_section")
        .annotate(submission_count=Count("submissions", distinct=True))
        .order_by("course_section__order", "order", "due_at", "title")
    )
    return {
        "activity_section_cards": activity_section_cards,
        "other_assignments": other_assignments,
        "total_assignment_count": Assignment.objects.filter(course=course).count(),
    }


@login_required
def section_students(request, slug, section_id):
    course, section, profile, can_manage = _section_access_context(request.user, slug, section_id)
    context = _section_dashboard_context(course, section, can_manage)
    context.update({
        "profile": profile,
        "course": course,
        "section": section,
        "can_manage": can_manage,
    })
    return render(request, "academics/section_students.html", context)


@login_required
def section_enrollment(request, slug, section_id):
    course, section, profile, can_manage = _section_access_context(request.user, slug, section_id)
    if not can_manage:
        raise PermissionDenied

    eligible_students = list(_eligible_students_for_course(course))
    eligible_student_ids = {student.id for student in eligible_students}

    if request.method == "POST":
        selected_ids = {
            int(student_id)
            for student_id in request.POST.getlist("selected_student_ids")
            if student_id.isdigit()
        }
        selected_ids &= eligible_student_ids
        current_ids = set(section.section_enrollments.values_list("student_id", flat=True))

        with transaction.atomic():
            remove_ids = current_ids - selected_ids
            if remove_ids:
                SectionEnrollment.objects.filter(section=section, student_id__in=remove_ids).delete()
                for student_id in remove_ids:
                    if not SectionEnrollment.objects.filter(section__course=course, student_id=student_id).exists():
                        Enrollment.objects.filter(course=course, student_id=student_id).delete()

            if selected_ids:
                SectionEnrollment.objects.filter(section__course=course, student_id__in=selected_ids).exclude(section=section).delete()
                for student_id in selected_ids:
                    SectionEnrollment.objects.get_or_create(section=section, student_id=student_id)
                    Enrollment.objects.get_or_create(course=course, student_id=student_id)

        added_count = len(selected_ids - current_ids)
        removed_count = len(current_ids - selected_ids)
        messages.success(request, f"Roster saved. Added {added_count}, removed {removed_count}.")
        return redirect("academics:section_students", slug=course.slug, section_id=section.id)

    context = _section_dashboard_context(course, section, can_manage)
    selected_ids = set(section.section_enrollments.values_list("student_id", flat=True))
    context.update({
        "profile": profile,
        "course": course,
        "section": section,
        "can_manage": can_manage,
        "available_students": [student for student in eligible_students if student.id not in selected_ids],
        "selected_students": [student for student in eligible_students if student.id in selected_ids],
    })
    return render(request, "academics/section_enrollment.html", context)


@login_required
def section_student_detail(request, slug, section_id, student_id):
    course, section, profile, can_manage = _section_access_context(request.user, slug, section_id)
    enrollment = get_object_or_404(
        SectionEnrollment.objects.select_related("student", "student__profile"),
        section=section,
        student_id=student_id,
    )
    student = enrollment.student
    submissions = list(Submission.objects.filter(
        Q(assignment__course_section=section) | Q(assignment__course_section__isnull=True),
        assignment__course=course,
        student=student,
    ).select_related("assignment").order_by("assignment__due_at", "assignment__title"))
    submitted_assignment_ids = {submission.assignment_id for submission in submissions}
    missing_assignments = [
        assignment
        for assignment in course.assignments.filter(Q(course_section=section) | Q(course_section__isnull=True)).order_by("activity_section__order", "course_section__order", "order", "due_at", "title")
        if assignment.id not in submitted_assignment_ids
    ]
    graded_submissions = [submission for submission in submissions if submission.score is not None]
    average_score = None
    if graded_submissions:
        average_score = round(
            sum(float(submission.score) for submission in graded_submissions) / len(graded_submissions),
            1,
        )

    context = _section_dashboard_context(course, section, can_manage)
    context.update({
        "profile": profile,
        "course": course,
        "section": section,
        "can_manage": can_manage,
        "section_enrollment": enrollment,
        "student": student,
        "submissions": submissions,
        "missing_assignments": missing_assignments,
        "submitted_count": len(submissions),
        "missing_count": len(missing_assignments),
        "graded_count": len(graded_submissions),
        "average_score": average_score,
    })
    return render(request, "academics/section_student_detail.html", context)


@login_required
def section_grading(request, slug, section_id):
    course, section, profile, can_manage = _section_access_context(request.user, slug, section_id)
    context = _section_dashboard_context(course, section, can_manage)
    context.update({
        "profile": profile,
        "course": course,
        "section": section,
        "can_manage": can_manage,
    })
    return render(request, "academics/section_grading.html", context)


@login_required
def course_activities(request, slug):
    course = get_object_or_404(
        Course.objects.select_related("instructor").prefetch_related("sections"),
        slug__iexact=slug,
    )
    if not _can_view_course(request.user, course):
        raise PermissionDenied
    profile = _profile_for(request.user)
    can_manage = _can_manage_course(request.user, course)
    return _render_activities_page(request, course, None, profile, can_manage)


@login_required
def section_activities(request, slug, section_id):
    course, section, profile, can_manage = _section_access_context(request.user, slug, section_id)
    return _render_activities_page(request, course, section, profile, can_manage)


def _render_activities_page(request, course, section, profile, can_manage):
    redirect_kwargs = {"slug": course.slug}
    redirect_name = "academics:course_activities"
    if section:
        redirect_name = "academics:section_activities"
        redirect_kwargs["section_id"] = section.id

    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied
        if request.POST.get("action") == "create_section":
            activity_section_form = ActivitySectionForm(request.POST)
            if activity_section_form.is_valid():
                activity_section = activity_section_form.save(commit=False)
                activity_section.course = course
                activity_section.order = course.activity_sections.count() + 1
                activity_section.save()
                messages.success(request, f"Section {activity_section.name} created.")
                return redirect(redirect_name, **redirect_kwargs)
        elif request.POST.get("action") == "edit_section":
            activity_section = get_object_or_404(
                ActivitySection,
                id=request.POST.get("activity_section_id"),
                course=course,
            )
            activity_section_form = ActivitySectionForm(request.POST, instance=activity_section)
            if activity_section_form.is_valid():
                activity_section_form.save()
                messages.success(request, f"Section {activity_section.name} updated.")
                return redirect(redirect_name, **redirect_kwargs)
        elif request.POST.get("action") == "delete_section":
            activity_section = get_object_or_404(
                ActivitySection,
                id=request.POST.get("activity_section_id"),
                course=course,
            )
            section_name = activity_section.name
            activity_section.delete()
            messages.success(request, f"Section {section_name} removed.")
            return redirect(redirect_name, **redirect_kwargs)
        else:
            return redirect(redirect_name, **redirect_kwargs)
    else:
        activity_section_form = ActivitySectionForm()

    context = _section_dashboard_context(course, section, can_manage) if section else {}
    context.update(_activity_board_context(course))
    context.update({
        "profile": profile,
        "course": course,
        "section": section,
        "can_manage": can_manage,
        "activity_section_form": activity_section_form,
    })
    return render(request, "academics/section_activities.html", context)


@login_required
def assignment_create(request, slug):
    course = get_object_or_404(Course.objects.prefetch_related("activity_sections", "sections"), slug__iexact=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    profile = _profile_for(request.user)
    initial = {}
    section_id = request.GET.get("section")
    if section_id and section_id.isdigit():
        initial["activity_section"] = course.activity_sections.filter(id=int(section_id)).first()
    course_section_id = request.GET.get("course_section")
    if course_section_id and course_section_id.isdigit():
        initial["course_section"] = course.sections.filter(id=int(course_section_id)).first()

    if request.method == "POST":
        assignment_form = AssignmentForm(request.POST, course=course)
        if assignment_form.is_valid():
            with transaction.atomic():
                assignment = assignment_form.save(commit=False)
                assignment.course = course
                assignment.instructor = request.user
                assignment.order = _next_assignment_order(course, assignment.activity_section)
                
                # Handle questions JSON
                questions_json = request.POST.get('questions_json', '[]')
                try:
                    questions_data = json.loads(questions_json)
                except json.JSONDecodeError:
                    questions_data = []

                total_points = sum(int(q.get('points', 0)) for q in questions_data)
                assignment.max_score = total_points
                
                assignment.save()

                for index, q_data in enumerate(questions_data):
                    Question.objects.create(
                        assignment=assignment,
                        text=q_data.get('text', ''),
                        question_type=q_data.get('type', 'text'),
                        points=int(q_data.get('points', 1)),
                        choices=q_data.get('choices', []),
                        correct_answer=str(q_data.get('correct_answer', '')),
                        order=index
                    )

                messages.success(request, f"{assignment.get_activity_type_display()} created.")
                return redirect("academics:assignment_detail", slug=course.slug, assignment_id=assignment.id)
    else:
        assignment_form = AssignmentForm(course=course, initial=initial)

    return render(request, "academics/assignment_form.html", {
        "profile": profile,
        "course": course,
        "can_manage": True,
        "assignment_form": assignment_form,
        "questions_json": "[]",
    })

@login_required
def assignment_edit(request, slug, assignment_id):
    course = get_object_or_404(Course, slug__iexact=slug)
    assignment = get_object_or_404(Assignment, id=assignment_id, course=course)
    
    if not _can_manage_course(request.user, course) and assignment.instructor != request.user:
        raise PermissionDenied
        
    profile = _profile_for(request.user)

    if request.method == "POST":
        assignment_form = AssignmentForm(request.POST, instance=assignment, course=course)
        if assignment_form.is_valid():
            with transaction.atomic():
                assignment = assignment_form.save(commit=False)
                
                questions_json = request.POST.get('questions_json', '[]')
                try:
                    questions_data = json.loads(questions_json)
                except json.JSONDecodeError:
                    questions_data = []

                total_points = sum(int(q.get('points', 0)) for q in questions_data)
                assignment.max_score = total_points
                assignment.save()

                # Clear existing questions and recreate them
                assignment.questions.all().delete()

                for index, q_data in enumerate(questions_data):
                    Question.objects.create(
                        assignment=assignment,
                        text=q_data.get('text', ''),
                        question_type=q_data.get('type', 'text'),
                        points=int(q_data.get('points', 1)),
                        choices=q_data.get('choices', []),
                        correct_answer=str(q_data.get('correct_answer', '')),
                        order=index
                    )

                messages.success(request, f"{assignment.get_activity_type_display()} updated.")
                return redirect("academics:assignment_detail", slug=course.slug, assignment_id=assignment.id)
    else:
        assignment_form = AssignmentForm(instance=assignment, course=course)
        
    existing_questions = []
    for q in assignment.questions.all():
        existing_questions.append({
            'text': q.text,
            'type': q.question_type,
            'points': q.points,
            'choices': q.choices,
            'correct_answer': q.correct_answer,
        })

    return render(request, "academics/assignment_form.html", {
        "profile": profile,
        "course": course,
        "can_manage": True,
        "assignment": assignment,
        "assignment_form": assignment_form,
        "questions_json": json.dumps(existing_questions),
    })

@login_required
def assignment_delete(request, slug, assignment_id):
    course = get_object_or_404(Course, slug__iexact=slug)
    assignment = get_object_or_404(Assignment, id=assignment_id, course=course)
    
    if not _can_manage_course(request.user, course) and assignment.instructor != request.user:
        raise PermissionDenied
        
    if request.method == "POST":
        activity_type = assignment.get_activity_type_display()
        assignment.delete()
        messages.success(request, f"{activity_type} deleted.")
        return redirect("academics:course_activities", slug=course.slug)
        
    return redirect("academics:assignment_detail", slug=course.slug, assignment_id=assignment.id)


@login_required
def assignment_detail(request, slug, assignment_id):
    course = get_object_or_404(Course.objects.prefetch_related("activity_sections", "sections"), slug__iexact=slug)
    if not _can_view_course(request.user, course):
        raise PermissionDenied
    assignment = get_object_or_404(
        Assignment.objects.select_related("course", "course_section", "activity_section").prefetch_related("submissions"),
        id=assignment_id,
        course=course,
    )
    profile = _profile_for(request.user)
    can_manage = _can_manage_course(request.user, course)

    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied
        if request.POST.get("action") == "copy_assignment":
            target_section_id = request.POST.get("target_section")
            target_section = get_object_or_404(CourseSection, id=target_section_id, course=course)
            copied_assignment, created = Assignment.objects.update_or_create(
                course=course,
                course_section=target_section,
                activity_section=assignment.activity_section,
                title=assignment.title,
                defaults={
                    "activity_type": assignment.activity_type,
                    "instructions": assignment.instructions,
                    "due_at": assignment.due_at,
                    "max_score": assignment.max_score,
                    "order": _next_assignment_order(course, assignment.activity_section),
                },
            )
            action_word = "copied to" if created else "updated in"
            messages.success(request, f"{assignment.title} {action_word} {target_section.name}.")
            return redirect("academics:assignment_detail", slug=course.slug, assignment_id=copied_assignment.id)
        if request.POST.get("action") == "delete_assignment":
            title = assignment.title
            redirect_kwargs = {"slug": course.slug}
            if assignment.course_section:
                section_id = assignment.course_section_id
                messages.success(request, f"{title} deleted.")
                assignment.delete()
                return redirect("academics:section_activities", slug=course.slug, section_id=section_id)
            assignment.delete()
            messages.success(request, f"{title} deleted.")
            return redirect("academics:course_activities", **redirect_kwargs)

    if assignment.course_section:
        section_enrollments = SectionEnrollment.objects.filter(section=assignment.course_section).select_related(
            "student", "student__profile"
        ).order_by("student__last_name", "student__first_name", "student__username")
        students = [enrollment.student for enrollment in section_enrollments]
    else:
        course_enrollments = Enrollment.objects.filter(course=course).select_related(
            "student", "student__profile"
        ).order_by("student__last_name", "student__first_name", "student__username")
        students = [enrollment.student for enrollment in course_enrollments]
    expected_label = assignment.activity_section.name if assignment.activity_section else "Other assignments"

    submissions = list(
        Submission.objects.filter(assignment=assignment)
        .select_related("student", "student__profile")
        .order_by("student__last_name", "student__first_name", "student__username")
    )
    submissions_by_student_id = {submission.student_id: submission for submission in submissions}
    submission_rows = [
        {
            "student": student,
            "submission": submissions_by_student_id.get(student.id),
        }
        for student in students
    ]
    copy_sections = course.sections.exclude(id=assignment.course_section_id).order_by("order", "name")

    return render(request, "academics/assignment_detail.html", {
        "profile": profile,
        "course": course,
        "assignment": assignment,
        "can_manage": can_manage,
        "submission_rows": submission_rows,
        "submitted_count": len(submissions),
        "expected_count": len(students),
        "expected_label": expected_label,
        "copy_sections": copy_sections,
    })


@login_required
def assignment_reorder(request, slug):
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)
    course = get_object_or_404(Course, slug__iexact=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    assignments = payload.get("assignments", [])
    section_ids = {
        int(item["section_id"])
        for item in assignments
        if str(item.get("section_id", "")).isdigit()
    }
    valid_sections = {
        activity_section.id: activity_section
        for activity_section in ActivitySection.objects.filter(course=course, id__in=section_ids)
    }

    with transaction.atomic():
        for item in assignments:
            assignment_id = item.get("id")
            if not str(assignment_id).isdigit():
                continue
            section_id = item.get("section_id")
            target_section = None
            if str(section_id).isdigit():
                target_section = valid_sections.get(int(section_id))
                if target_section is None:
                    continue
            Assignment.objects.filter(course=course, id=int(assignment_id)).update(
                activity_section=target_section,
                order=int(item.get("order", 0)),
            )

    return JsonResponse({"ok": True})


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

from django.contrib.auth import get_user_model, login
from .forms import SchoolForm, UserCreationForm, SignupForm
from .models import School

def _can_manage_platform(user):
    return user.is_authenticated and hasattr(user, 'profile') and user.profile.role == Profile.Role.PLATFORM_ADMIN

def signup_view(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["school_code"]
            role = form.cleaned_data["role"]
            # Resolve the school based on which code was used
            if role == Profile.Role.STUDENT:
                school = School.objects.get(school_code=code)
            elif role == Profile.Role.INSTRUCTOR:
                school = School.objects.get(teacher_code=code)
            else:
                school = School.objects.get(admin_code=code)

            User = get_user_model()
            if User.objects.filter(email=form.cleaned_data["email"]).exists():
                messages.error(request, "Email already in use.")
                return render(request, "registration/signup.html", {"form": form})

            user = User.objects.create_user(
                username=form.cleaned_data["email"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
            )
            Profile.objects.create(
                user=user,
                role=role,
                school=school
            )
            login(request, user)
            messages.success(request, f"Welcome! You have joined {school.name}.")
            return redirect("academics:dashboard")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form})

@login_required
def platform_admin_dashboard(request):
    if not _can_manage_platform(request.user):
        raise PermissionDenied

    schools = School.objects.all().order_by("-created_at").annotate(
        user_count=Count("profiles")
    )
    User = get_user_model()
    users = User.objects.filter(profile__isnull=False).select_related("profile", "profile__school").order_by("-date_joined")

    return render(request, "academics/dashboards/platform_admin.html", {
        "profile": _profile_for(request.user),
        "schools": schools,
        "users": users
    })

@login_required
def manage_school(request, school_id):
    if not _can_manage_platform(request.user):
        raise PermissionDenied
    school = get_object_or_404(School, pk=school_id)
    profiles = Profile.objects.filter(school=school).select_related("user").order_by("role", "user__last_name")
    role_choices = [
        (Profile.Role.STUDENT, "Student"),
        (Profile.Role.INSTRUCTOR, "Teacher/Instructor"),
        (Profile.Role.ACADEMIC_ADMIN, "Academic Admin"),
    ]
    return render(request, "academics/platform_admin/manage_school.html", {
        "profile": _profile_for(request.user),
        "school": school,
        "profiles": profiles,
        "role_choices": role_choices,
    })

@login_required
def edit_school(request, school_id):
    if not _can_manage_platform(request.user):
        raise PermissionDenied
    school = get_object_or_404(School, pk=school_id)
    if request.method == "POST":
        form = SchoolForm(request.POST, instance=school)
        if form.is_valid():
            form.save()
            messages.success(request, "School updated successfully.")
            return redirect("academics:manage_school", school_id=school.pk)
    else:
        form = SchoolForm(instance=school)
    return render(request, "academics/platform_admin/edit_school.html", {
        "profile": _profile_for(request.user),
        "form": form,
        "school": school,
    })

@login_required
def delete_school(request, school_id):
    if not _can_manage_platform(request.user):
        raise PermissionDenied
    school = get_object_or_404(School, pk=school_id)
    if request.method == "POST":
        school.delete()
        messages.success(request, f"School '{school.name}' has been deleted.")
        return redirect("academics:platform_admin_dashboard")
    return render(request, "academics/platform_admin/delete_school.html", {
        "profile": _profile_for(request.user),
        "school": school,
    })

@login_required
def remove_user_from_school(request, school_id, user_id):
    if not _can_manage_platform(request.user):
        raise PermissionDenied
    if request.method == "POST":
        profile = get_object_or_404(Profile, user_id=user_id, school_id=school_id)
        profile.school = None
        profile.save()
        messages.success(request, "User removed from school.")
    return redirect("academics:manage_school", school_id=school_id)

@login_required
def change_user_role(request, school_id, user_id):
    if not _can_manage_platform(request.user):
        raise PermissionDenied
    if request.method == "POST":
        profile = get_object_or_404(Profile, user_id=user_id, school_id=school_id)
        new_role = request.POST.get("role")
        allowed = [Profile.Role.STUDENT, Profile.Role.INSTRUCTOR, Profile.Role.ACADEMIC_ADMIN]
        if new_role in allowed:
            profile.role = new_role
            profile.save()
            messages.success(request, f"Role updated to {profile.get_role_display()}.")
        else:
            messages.error(request, "Invalid role.")
    return redirect("academics:manage_school", school_id=school_id)

@login_required
def create_school(request):
    if not _can_manage_platform(request.user):
        raise PermissionDenied

    if request.method == "POST":
        form = SchoolForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "School created successfully.")
            return redirect("academics:platform_admin_dashboard")
    else:
        form = SchoolForm()
    return render(request, "academics/platform_admin/create_school.html", {
        "profile": _profile_for(request.user),
        "form": form,
    })

@login_required
def create_user(request):
    if not _can_manage_platform(request.user):
        raise PermissionDenied

    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            User = get_user_model()
            if User.objects.filter(email=form.cleaned_data["email"]).exists():
                messages.error(request, "Email already in use.")
            else:
                user = User.objects.create_user(
                    username=form.cleaned_data["email"],
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password"],
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                )
                Profile.objects.create(
                    user=user,
                    role=form.cleaned_data["role"],
                    school=form.cleaned_data["school"]
                )
                messages.success(request, f"Account created for {user.email}.")
                return redirect("academics:platform_admin_dashboard")
    else:
        form = UserCreationForm()
    return render(request, "academics/platform_admin/create_user.html", {
        "profile": _profile_for(request.user),
        "form": form,
    })

@login_required
def ai_lesson_plan(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    
    if request.method == "POST":
        topic = request.POST.get("topic", "")
        modules = request.POST.get("modules", "1")
        duration = request.POST.get("duration", "")
        instructions = request.POST.get("instructions", "")
        materials_ids = request.POST.getlist("materials")

        duration_val = int(duration) if duration.isdigit() else None
        modules_val = int(modules) if modules.isdigit() else 1
        title = topic if topic else f"Lesson Plan - {timezone.now().strftime('%Y-%m-%d %H:%M')}"

        plan = GeneratedLessonPlan.objects.create(
            course=course,
            author=request.user,
            title=title,
            topic=topic,
            modules=modules_val,
            duration_minutes=duration_val,
            content="",
            status=GeneratedLessonPlan.Status.QUEUED
        )
        
        from .tasks import generate_lesson_plan_task
        generate_lesson_plan_task.delay(
            plan.id,
            materials_ids,
            topic,
            modules,
            duration,
            instructions
        )

        messages.info(request, "Lesson plan generation started in the background.")
        return redirect("academics:lesson_plan_detail", slug=course.slug, plan_id=plan.id)

    materials = course.materials.all().order_by("-created_at")
    return render(request, "academics/ai_lesson_plan.html", {
        "course": course,
        "materials": materials,
        "profile": _profile_for(request.user),
    })

@login_required
def lesson_plan_list(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    
    plans = course.generated_lesson_plans.all()
    return render(request, "academics/lesson_plan_list.html", {
        "course": course,
        "plans": plans,
        "profile": _profile_for(request.user),
    })

@login_required
def lesson_plan_detail(request, slug, plan_id):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    
    plan = get_object_or_404(GeneratedLessonPlan, pk=plan_id, course=course)

    if request.method == "POST":
        content = request.POST.get("content")
        title = request.POST.get("title")
        if content and title:
            plan.content = content
            plan.title = title
            plan.save()
            messages.success(request, "Lesson plan updated successfully.")
            return redirect("academics:lesson_plan_detail", slug=course.slug, plan_id=plan.id)

    return render(request, "academics/lesson_plan_detail.html", {
        "course": course,
        "plan": plan,
        "profile": _profile_for(request.user),
    })

@login_required
def lesson_plan_delete(request, slug, plan_id):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    
    plan = get_object_or_404(GeneratedLessonPlan, pk=plan_id, course=course)
    
    if request.method == "POST":
        plan.delete()
        messages.success(request, "Lesson plan deleted.")
        return redirect("academics:lesson_plan_list", slug=course.slug)
    
    # Can render a confirmation or redirect back
    return redirect("academics:lesson_plan_detail", slug=course.slug, plan_id=plan.id)

@login_required
def ai_activity_sheets(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    return render(request, "academics/ai_activity_sheets.html", {
        "course": course,
        "profile": _profile_for(request.user),
    })


from .models import CourseWebsiteFilter, ResourceTag
import json

@login_required
def toggle_resource_reject(request, slug, session_id, resource_id):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    if request.method == "POST":
        resource = get_object_or_404(SuggestedResource, id=resource_id, session__course=course)
        resource.is_rejected = not resource.is_rejected
        if resource.is_rejected:
            resource.is_approved = False # Mutual exclusion
        resource.save()
        return JsonResponse({"status": "success", "is_rejected": resource.is_rejected})
    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)

@login_required
def update_resource_tags(request, slug, session_id, resource_id):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    if request.method == "POST":
        resource = get_object_or_404(SuggestedResource, id=resource_id, session__course=course)
        try:
            data = json.loads(request.body)
            tag_ids = data.get("tags", [])
            resource.tags.set(tag_ids)
            return JsonResponse({"status": "success"})
        except json.JSONDecodeError:
            pass
    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)

@login_required
def manage_website_filters(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    if request.method == "POST":
        urls = request.POST.get("urls", "")
        filter_type = request.POST.get("filter_type", "trusted")
        for line in urls.split("\n"):
            line = line.strip()
            if line:
                CourseWebsiteFilter.objects.get_or_create(course=course, url=line, filter_type=filter_type)
        messages.success(request, "Website filters updated.")
        return redirect("academics:resource_assistant_index", slug=slug)
    return redirect("academics:resource_assistant_index", slug=slug)

@login_required
def delete_website_filter(request, slug, filter_id):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    if request.method == "POST":
        flt = get_object_or_404(CourseWebsiteFilter, id=filter_id, course=course)
        flt.delete()
        messages.success(request, "Filter deleted.")
    return redirect("academics:resource_assistant_index", slug=slug)

@login_required
def manage_resource_tags(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        color = request.POST.get("color", "#3b82f6").strip()
        if name:
            ResourceTag.objects.get_or_create(course=course, name=name, defaults={"color": color})
            messages.success(request, "Tag created.")
        return redirect("academics:resource_assistant_index", slug=slug)
    return redirect("academics:resource_assistant_index", slug=slug)

@login_required
def delete_resource_tag(request, slug, tag_id):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    if request.method == "POST":
        tag = get_object_or_404(ResourceTag, id=tag_id, course=course)
        tag.delete()
        messages.success(request, "Tag deleted.")
    return redirect("academics:resource_assistant_index", slug=slug)

@login_required
def resource_assistant_index(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    
    sessions = ResourceAssistantSession.objects.filter(course=course, author=request.user).order_by("-created_at")
    approved_resources = SuggestedResource.objects.filter(session__course=course, session__author=request.user, is_approved=True, is_rejected=False).order_by("-created_at")
    website_filters = CourseWebsiteFilter.objects.filter(course=course)
    resource_tags = ResourceTag.objects.filter(course=course)
    lesson_plans = course.generated_lesson_plans.filter(author=request.user)
    materials = course.materials.filter(is_processed=True)
    
    return render(request, "academics/ai_resource_assistant.html", {
        "course": course,
        "sessions": sessions,
        "show_form": False,
        "approved_resources": approved_resources,
        "website_filters": website_filters,
        "resource_tags": resource_tags,
        "lesson_plans": lesson_plans,
        "materials": materials,
        "profile": _profile_for(request.user),
    })

@login_required
def ai_resource_assistant(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    
    sessions = ResourceAssistantSession.objects.filter(course=course, author=request.user).order_by("-created_at")
    
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
            
            include_videos = request.POST.get("include_videos") == "true"
            include_books = request.POST.get("include_books") == "true"
            if not include_videos and not include_books:
                include_videos = True
                include_books = True
            
            # Start background task
            from .tasks import generate_resources_task
            generate_resources_task.delay(session.id, include_videos, include_books)
            
            return redirect("academics:resource_session_detail", slug=slug, session_id=session.id)
            
    # Load extra context for the form and aggregated views
    approved_resources = SuggestedResource.objects.filter(session__course=course, session__author=request.user, is_approved=True, is_rejected=False).order_by("-created_at")
    website_filters = CourseWebsiteFilter.objects.filter(course=course)
    resource_tags = ResourceTag.objects.filter(course=course)
    lesson_plans = course.generated_lesson_plans.filter(author=request.user)
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
        "profile": _profile_for(request.user),
    })

@login_required
def resource_session_detail(request, slug, session_id):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    session = get_object_or_404(ResourceAssistantSession, id=session_id, course=course)
    sessions = ResourceAssistantSession.objects.filter(course=course, author=request.user).order_by("-created_at")
    
    return render(request, "academics/resource_session_detail.html", {
        "course": course,
        "session": session,
        "sessions": sessions,
        "profile": _profile_for(request.user),
    })

@login_required
def resource_session_delete(request, slug, session_id):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    if request.method == "POST":
        session = get_object_or_404(ResourceAssistantSession, id=session_id, course=course)
        session.delete()
        messages.success(request, "Resource session deleted.")
    return redirect("academics:resource_assistant_index", slug=slug)

@login_required
def toggle_resource_approval(request, slug, session_id, resource_id):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    if request.method == "POST":
        resource = get_object_or_404(SuggestedResource, id=resource_id, session__course=course)
        resource.is_approved = not resource.is_approved
        if resource.is_approved:
            resource.is_rejected = False # Mutual exclusion
        resource.save()
        return JsonResponse({"status": "success", "is_approved": resource.is_approved})
    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)

@login_required
def activity_sheet_detail(request, slug, sheet_id):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    
    from academics.models import GeneratedActivitySheet
    sheet = get_object_or_404(GeneratedActivitySheet, id=sheet_id, course=course)
    all_sheets = GeneratedActivitySheet.objects.filter(course=course).order_by("-created_at")
    
    if request.method == "POST":
        sheet.title = request.POST.get("title", sheet.title)
        sheet.content = request.POST.get("content", sheet.content)
        sheet.save()
        messages.success(request, "Activity sheet updated.")
        return redirect("academics:activity_sheet_detail", slug=slug, sheet_id=sheet.id)
    
    return render(request, "academics/activity_sheet_detail.html", {
        "course": course,
        "sheet": sheet,
        "all_sheets": all_sheets,
    })

@login_required
def activity_sheet_delete(request, slug, sheet_id):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    from academics.models import GeneratedActivitySheet
    if request.method == "POST":
        sheet = get_object_or_404(GeneratedActivitySheet, id=sheet_id, course=course)
        sheet.delete()
        messages.success(request, "Activity sheet deleted.")
    return redirect("academics:ai_activity_sheets", slug=slug)

@login_required
def delete_approved_resource(request, slug, resource_id):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    if request.method == "POST":
        resource = get_object_or_404(SuggestedResource, id=resource_id, session__course=course)
        resource.delete()
        messages.success(request, "Resource deleted.")
    return redirect("academics:resource_assistant_index", slug=slug)

@login_required
def remove_duplicate_resources(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    if request.method == "POST":
        resources = SuggestedResource.objects.filter(session__course=course, is_approved=True).order_by("-created_at")
        seen_urls = set()
        deleted_count = 0
        for r in resources:
            if r.url in seen_urls:
                r.delete()
                deleted_count += 1
            else:
                seen_urls.add(r.url)
        messages.success(request, f"Removed {deleted_count} duplicate resource(s).")
    return redirect("academics:resource_assistant_index", slug=slug)

@login_required
def manual_add_resource(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    if request.method == "POST":
        url = request.POST.get("url")
        title = request.POST.get("title")
        resource_type = request.POST.get("resource_type", "book")
        description = request.POST.get("description", "")
        
        session, created = ResourceAssistantSession.objects.get_or_create(
            course=course,
            topic="Manually Added Resources",
            defaults={"status": "completed"}
        )
        
        SuggestedResource.objects.create(
            session=session,
            title=title,
            url=url,
            resource_type=resource_type,
            description=description,
            is_approved=True
        )
        messages.success(request, "Resource added successfully.")
        
    return redirect("academics:resource_assistant_index", slug=slug)

@login_required
def lesson_plan_index(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    
    latest_plan = course.generated_lesson_plans.first()
    if latest_plan:
        return redirect("academics:lesson_plan_detail", slug=course.slug, plan_id=latest_plan.id)
    return redirect("academics:ai_lesson_plan", slug=course.slug)

@login_required
def activity_sheet_index(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
    
    latest_sheet = course.generated_activity_sheets.first()
    if latest_sheet:
        return redirect("academics:activity_sheet_detail", slug=course.slug, sheet_id=latest_sheet.id)
    return redirect("academics:ai_activity_sheets", slug=course.slug)

@login_required
def sync_resource_settings(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_manage_course(request.user, course):
        raise PermissionDenied
        
    if request.method == "POST":
        payload = request.POST.get("payload")
        if payload:
            try:
                data = json.loads(payload)
                
                # 1. Sync Website Filters (Safe to wipe and recreate)
                CourseWebsiteFilter.objects.filter(course=course).delete()
                for url in data.get("trusted", []):
                    if url.strip():
                        CourseWebsiteFilter.objects.create(course=course, url=url.strip(), filter_type="trusted")
                for url in data.get("excluded", []):
                    if url.strip():
                        CourseWebsiteFilter.objects.create(course=course, url=url.strip(), filter_type="excluded")
                        
                # 2. Sync Tags (Preserve IDs to avoid breaking ManyToMany relationships)
                incoming_tags = data.get("tags", [])
                incoming_tag_ids = [t["id"] for t in incoming_tags if t.get("id")]
                
                # Delete tags that are no longer in the payload
                ResourceTag.objects.filter(course=course).exclude(id__in=incoming_tag_ids).delete()
                
                # Update existing and create new
                for t in incoming_tags:
                    name = t.get("name", "").strip()
                    color = t.get("color", "#3b82f6").strip()
                    if not name:
                        continue
                        
                    if t.get("id"):
                        # Update existing
                        tag = ResourceTag.objects.filter(id=t["id"], course=course).first()
                        if tag:
                            tag.name = name
                            tag.color = color
                            tag.save()
                    else:
                        # Create new
                        ResourceTag.objects.create(course=course, name=name, color=color)
                        
                messages.success(request, "Links and tags saved successfully.")
            except json.JSONDecodeError:
                messages.error(request, "Failed to parse settings.")
                
    return redirect("academics:resource_assistant_index", slug=slug)
