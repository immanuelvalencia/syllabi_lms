from django.contrib import admin

from .models import (
    ActivitySection,
    AiToolRequest,
    Announcement,
    Assignment,
    Course,
    CourseSection,
    Enrollment,
    Lesson,
    Profile,
    School,
    SectionEnrollment,
    Submission,
)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "school_code", "teacher_code", "admin_code", "created_at")
    search_fields = ("name", "school_code", "teacher_code", "admin_code")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "school", "department", "id_number", "grade_level")
    list_filter = ("role", "school", "grade_level", "department")
    search_fields = ("user__username", "user__first_name", "user__last_name", "id_number", "school__name")


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


@admin.register(ActivitySection)
class ActivitySectionAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "grading_weight", "order")
    list_filter = ("course",)
    search_fields = ("name", "course__code", "course__title")


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
    list_display = ("course", "course_section", "activity_section", "activity_type", "title", "due_at", "max_score", "order")
    list_filter = ("course", "course_section", "activity_section", "activity_type", "due_at")
    search_fields = ("title", "course__code", "course__title", "course_section__name", "activity_section__name")


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
