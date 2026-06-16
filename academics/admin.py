from django.contrib import admin

from .models import (
    AiToolRequest,
    Announcement,
    Assignment,
    Course,
    CourseSection,
    Enrollment,
    Lesson,
    Profile,
    SectionEnrollment,
    Submission,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "department", "student_id", "staff_id")
    list_filter = ("role", "department")
    search_fields = ("user__username", "user__first_name", "user__last_name", "student_id", "staff_id")


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 1


class CourseSectionInline(admin.TabularInline):
    model = CourseSection
    extra = 1


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "public_id", "instructor", "department", "is_active")
    list_filter = ("is_active", "department")
    search_fields = ("code", "title", "instructor__username")
    readonly_fields = ("public_id",)
    inlines = [CourseSectionInline, LessonInline, AssignmentInline]


@admin.register(CourseSection)
class CourseSectionAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "meeting_days", "start_time", "end_time", "location")
    list_filter = ("course",)
    search_fields = ("name", "course__code", "course__title")
    readonly_fields = ("public_id",)


@admin.register(SectionEnrollment)
class SectionEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "section", "enrolled_at")
    list_filter = ("section__course", "section")
    search_fields = ("student__username", "student__first_name", "student__last_name", "section__name")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "progress_percent", "enrolled_at", "completed_at")
    list_filter = ("course",)
    search_fields = ("student__username", "course__code", "course__title")


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("course", "order", "title", "is_published")
    list_filter = ("is_published", "course")
    search_fields = ("title", "course__code", "course__title")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("course", "title", "due_at", "max_score")
    list_filter = ("course", "due_at")
    search_fields = ("title", "course__code", "course__title")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("assignment", "student", "score", "submitted_at", "graded_at")
    list_filter = ("assignment__course", "graded_at")
    search_fields = ("student__username", "assignment__title")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "audience_all", "author", "created_at")
    list_filter = ("audience_all", "course")
    search_fields = ("title", "body", "author__username")


@admin.register(AiToolRequest)
class AiToolRequestAdmin(admin.ModelAdmin):
    list_display = ("tool_type", "user", "status", "created_at", "completed_at")
    list_filter = ("tool_type", "status")
    search_fields = ("user__username", "prompt", "result")
