from django.urls import path

from . import views

app_name = "academics"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("dashboard/", views.dashboard, name="dashboard_home"),
    path("student/dashboard/", views.student_dashboard, name="student_dashboard"),
    path("teacher/dashboard/", views.instructor_dashboard, name="instructor_dashboard"),
    path("teacher/courses/", views.teacher_courses, name="teacher_courses"),
    path("teacher/courses/new/", views.create_teacher_course, name="create_teacher_course"),
    path("academic-admin/dashboard/", views.academic_admin_dashboard, name="academic_admin_dashboard"),
    path("courses/<slug:slug>/", views.course_detail, name="course_detail"),
    path("courses/<slug:slug>/analytics.pdf", views.course_analytics_pdf, name="course_analytics_pdf"),
    path("courses/<slug:slug>/sections/<int:section_id>/", views.section_detail, name="section_detail"),
    path("materials/<int:material_id>/delete/", views.delete_course_material, name="delete_course_material"),
    path("ai-tools/request/", views.create_ai_tool_request, name="create_ai_tool_request"),
]
