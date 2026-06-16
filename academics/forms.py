from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Course, CourseMaterial, CourseSection, Profile


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["title", "code", "school_year", "grade_level", "description"]
        labels = {
            "title": "Course name",
            "code": "Course code",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        current_year = timezone.now().year
        year_choices = [("", "---------")]
        for year in range(current_year - 1, current_year + 5):
            year_choices.append((f"{year}-{year+1}", f"{year}-{year+1}"))
            
        self.fields["school_year"] = forms.ChoiceField(choices=year_choices, required=False)
        self.fields["school_year"].widget.attrs.setdefault("class", "form-select")
        
        for field_name, field in self.fields.items():
            if field_name != "school_year":
                field.widget.attrs.setdefault("class", "form-control")


class CourseSectionForm(forms.ModelForm):
    DAYS_CHOICES = [
        ("Mon", "Monday"),
        ("Tue", "Tuesday"),
        ("Wed", "Wednesday"),
        ("Thu", "Thursday"),
        ("Fri", "Friday"),
        ("Sat", "Saturday"),
        ("Sun", "Sunday"),
    ]
    
    meeting_days = forms.MultipleChoiceField(
        choices=DAYS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Meeting Days"
    )

    class Meta:
        model = CourseSection
        fields = ["name", "schedule_title", "meeting_days", "start_time", "end_time", "location"]
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def clean_meeting_days(self):
        data = self.cleaned_data.get("meeting_days")
        if data:
            return ", ".join(data)
        return ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.meeting_days:
            self.initial['meeting_days'] = [day.strip() for day in self.instance.meeting_days.split(",")]
            
        for field_name, field in self.fields.items():
            if field_name != "meeting_days":
                field.widget.attrs.setdefault("class", "form-control")


class SectionEnrollmentForm(forms.Form):
    student = forms.ModelChoiceField(queryset=get_user_model().objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields["student"].queryset = User.objects.filter(
            profile__role=Profile.Role.STUDENT,
            is_active=True,
        ).order_by("first_name", "last_name", "username")
        self.fields["student"].widget.attrs.setdefault("class", "form-select")

class CourseMaterialForm(forms.ModelForm):
    class Meta:
        model = CourseMaterial
        fields = ["title", "category", "file"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
