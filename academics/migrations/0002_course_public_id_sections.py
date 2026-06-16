import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def populate_course_public_ids(apps, schema_editor):
    Course = apps.get_model("academics", "Course")
    for course in Course.objects.filter(public_id__isnull=True):
        course.public_id = uuid.uuid4()
        course.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="course",
            name="public_id",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(populate_course_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="course",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.CreateModel(
            name="CourseSection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("schedule_title", models.CharField(blank=True, max_length=160)),
                ("meeting_days", models.CharField(blank=True, max_length=120)),
                ("start_time", models.TimeField(blank=True, null=True)),
                ("end_time", models.TimeField(blank=True, null=True)),
                ("location", models.CharField(blank=True, max_length=160)),
                ("order", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("course", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sections", to="academics.course")),
            ],
            options={
                "ordering": ["course", "order", "name"],
                "unique_together": {("course", "name")},
            },
        ),
        migrations.CreateModel(
            name="SectionEnrollment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enrolled_at", models.DateTimeField(auto_now_add=True)),
                ("section", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="section_enrollments", to="academics.coursesection")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="section_enrollments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["section__course__code", "section__name", "student__username"],
                "unique_together": {("section", "student")},
            },
        ),
    ]
