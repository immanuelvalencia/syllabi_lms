from django.db import migrations, models
import academics.models
import django.utils.crypto


def populate_assignment_public_ids(apps, schema_editor):
    Assignment = apps.get_model("academics", "Assignment")
    existing_ids = set(
        Assignment.objects.exclude(public_id__isnull=True)
        .exclude(public_id="")
        .values_list("public_id", flat=True)
    )
    for assignment in Assignment.objects.filter(models.Q(public_id__isnull=True) | models.Q(public_id="")):
        public_id = django.utils.crypto.get_random_string(10)
        while public_id in existing_ids:
            public_id = django.utils.crypto.get_random_string(10)
        existing_ids.add(public_id)
        assignment.public_id = public_id
        assignment.save(update_fields=["public_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0023_question_answer_settings_question_content_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignment",
            name="public_id",
            field=models.CharField(blank=True, editable=False, max_length=36, null=True, unique=True),
        ),
        migrations.RunPython(populate_assignment_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="assignment",
            name="public_id",
            field=models.CharField(default=academics.models.generate_short_id, editable=False, max_length=36, unique=True),
        ),
    ]
