from datetime import timedelta
import os

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.text import slugify

def generate_short_id():
    return get_random_string(10)


class Profile(models.Model):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        INSTRUCTOR = "instructor", "Instructor"
        ACADEMIC_ADMIN = "academic_admin", "Academic Admin"
        PLATFORM_ADMIN = "platform_admin", "Platform Admin"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.STUDENT)
    department = models.CharField(max_length=120, blank=True)
    student_id = models.CharField(max_length=64, blank=True)
    staff_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"


class Course(models.Model):
    public_id = models.CharField(max_length=36, default=generate_short_id, editable=False, unique=True)
    title = models.CharField(max_length=180)
    code = models.CharField(max_length=32, unique=True)
    slug = models.SlugField(max_length=50, blank=True, null=True, unique=True)
    description = models.TextField(blank=True)
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="teaching_courses",
    )
    department = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    school_year = models.CharField(max_length=20, blank=True)
    grade_level = models.CharField(max_length=50, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.title}"

    def save(self, *args, **kwargs):
        if not self.slug or self.slug != slugify(self.code):
            self.slug = slugify(self.code)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("academics:course_detail", args=[self.slug or self.code])


class CourseSection(models.Model):
    public_id = models.CharField(max_length=36, default=generate_short_id, editable=False, unique=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sections")
    name = models.CharField(max_length=120)
    schedule_title = models.CharField(max_length=160, blank=True)
    meeting_days = models.CharField(max_length=120, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=160, blank=True)
    order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["course", "order", "name"]
        unique_together = [("course", "name")]

    def __str__(self):
        return f"{self.course.code} - {self.name}"

    def get_absolute_url(self):
        return reverse("academics:section_detail", args=[self.course.slug or self.course.code, self.id])


class SectionEnrollment(models.Model):
    section = models.ForeignKey(
        CourseSection,
        on_delete=models.CASCADE,
        related_name="section_enrollments",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="section_enrollments",
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("section", "student")]
        ordering = ["section__course__code", "section__name", "student__username"]

    def __str__(self):
        return f"{self.student.username} in {self.section}"


class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=180)
    summary = models.TextField(blank=True)
    resource_url = models.URLField(blank=True)
    order = models.PositiveIntegerField(default=1)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["course", "order", "title"]
        unique_together = [("course", "order")]

    def __str__(self):
        return f"{self.course.code}: {self.title}"


class Enrollment(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    progress_percent = models.PositiveSmallIntegerField(default=0)
    current_lesson = models.ForeignKey(
        Lesson,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("student", "course")]
        ordering = ["course__code"]

    def __str__(self):
        return f"{self.student.username} in {self.course.code}"


class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assignments")
    title = models.CharField(max_length=180)
    instructions = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    max_score = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_at", "title"]

    def __str__(self):
        return f"{self.course.code}: {self.title}"

    @property
    def is_due_soon(self):
        if not self.due_at:
            return False
        return timezone.now() <= self.due_at <= timezone.now() + timedelta(days=7)


class Submission(models.Model):
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    content = models.TextField(blank=True)
    attachment_url = models.URLField(blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("assignment", "student")]
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.student.username} - {self.assignment.title}"


class Announcement(models.Model):
    audience_all = models.BooleanField(default=False)
    course = models.ForeignKey(
        Course,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="announcements",
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    title = models.CharField(max_length=180)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class AiToolRequest(models.Model):
    class ToolType(models.TextChoices):
        STUDY_PLAN = "study_plan", "Study Plan"
        QUIZ_GENERATOR = "quiz_generator", "Quiz Generator"
        LESSON_SUMMARY = "lesson_summary", "Lesson Summary"
        FEEDBACK_ASSISTANT = "feedback_assistant", "Feedback Assistant"
        RISK_INSIGHTS = "risk_insights", "Risk Insights"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_tool_requests",
    )
    tool_type = models.CharField(max_length=40, choices=ToolType.choices)
    prompt = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    result = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_tool_type_display()} for {self.user.username} ({self.status})"

class CourseMaterial(models.Model):
    class CategoryChoices(models.TextChoices):
        READING = "reading", "Reading Material"
        LECTURE = "lecture", "Lecture Slides/Notes"
        ASSIGNMENT = "assignment", "Assignment Resource"
        SYLLABUS = "syllabus", "Syllabus"
        OTHER = "other", "Other"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="materials")
    file = models.FileField(upload_to="course_materials/")
    title = models.CharField(max_length=180, blank=True)
    category = models.CharField(max_length=50, choices=CategoryChoices.choices, default=CategoryChoices.OTHER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or self.file.name

    @property
    def display_name(self):
        import os
        if self.title:
            return self.title
        return os.path.basename(self.file.name)

    @property
    def file_extension(self):
        name, extension = os.path.splitext(self.file.name)
        return extension.lower()

    @property
    def material_type(self):
        ext = self.file_extension
        if ext == ".pdf":
            return "pdf"
        elif ext in [".mp4", ".mov", ".avi", ".webm"]:
            return "video"
        elif ext in [".ppt", ".pptx"]:
            return "presentation"
        elif ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            return "image"
        return "document"
