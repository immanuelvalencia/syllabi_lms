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
    path("platform-admin/dashboard/", views.platform_admin_dashboard, name="platform_admin_dashboard"),
    path("platform-admin/schools/new/", views.create_school, name="create_school"),
    path("platform-admin/schools/<int:school_id>/", views.manage_school, name="manage_school"),
    path("platform-admin/schools/<int:school_id>/edit/", views.edit_school, name="edit_school"),
    path("platform-admin/schools/<int:school_id>/delete/", views.delete_school, name="delete_school"),
    path("platform-admin/schools/<int:school_id>/users/<int:user_id>/remove/", views.remove_user_from_school, name="remove_user_from_school"),
    path("platform-admin/schools/<int:school_id>/users/<int:user_id>/role/", views.change_user_role, name="change_user_role"),
    path("platform-admin/users/new/", views.create_user, name="create_user"),
    path("courses/<slug:slug>/", views.course_detail, name="course_detail"),
    path("courses/<slug:slug>/analytics.pdf", views.course_analytics_pdf, name="course_analytics_pdf"),
    path("courses/<slug:slug>/sections/<int:section_id>/", views.section_detail, name="section_detail"),
    path("materials/<int:material_id>/delete/", views.delete_course_material, name="delete_course_material"),
    path("materials/<int:material_id>/analyze/", views.analyze_material, name="analyze_material"),
    path("ai-tools/request/", views.create_ai_tool_request, name="create_ai_tool_request"),
    path("ai-tasks/", views.ai_tasks_list, name="ai_tasks_list"),
    path("courses/<slug:slug>/ai-generate/", views.ai_generate, name="ai_generate"),
    path("courses/<slug:slug>/lesson-plans/", views.lesson_plan_list, name="lesson_plan_list"),
    path("courses/<slug:slug>/lesson-plans/<int:plan_id>/", views.lesson_plan_detail, name="lesson_plan_detail"),
    path("courses/<slug:slug>/lesson-plans/<int:plan_id>/delete/", views.lesson_plan_delete, name="lesson_plan_delete"),
    path("courses/<slug:slug>/ai-lesson-plan/", views.ai_lesson_plan, name="ai_lesson_plan"),
    path("courses/<slug:slug>/ai-activity-sheets/", views.ai_activity_sheets, name="ai_activity_sheets"),
]
