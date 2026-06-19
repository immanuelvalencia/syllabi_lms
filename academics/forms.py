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
        self.fields["school_year"].widget.attrs.setdefault("class", "block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 shadow-sm outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 sm:max-w-xs sm:text-sm sm:leading-6")
        
        for field_name, field in self.fields.items():
            if field_name != "school_year":
                field.widget.attrs.setdefault("class", "block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 shadow-sm outline-none placeholder:text-gray-400 focus:border-gray-900 focus:ring-1 focus:ring-gray-900 sm:text-sm sm:leading-6")


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
        widget=forms.CheckboxSelectMultiple(attrs={"class": "h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-600"}),
        required=False,
        label="Meeting Days"
    )

    class Meta:
        model = CourseSection
        fields = ["name", "meeting_days", "start_time", "end_time", "location"]
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
                field.widget.attrs.setdefault("class", "block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 shadow-sm outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 sm:text-sm sm:leading-6")


class SectionEnrollmentForm(forms.Form):
    student = forms.ModelChoiceField(queryset=get_user_model().objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields["student"].queryset = User.objects.filter(
            profile__role=Profile.Role.STUDENT,
            is_active=True,
        ).order_by("first_name", "last_name", "username")
        self.fields["student"].widget.attrs.setdefault("class", "block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 shadow-sm outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 sm:text-sm sm:leading-6")

class CourseMaterialForm(forms.ModelForm):
    class Meta:
        model = CourseMaterial
        fields = ["title", "category", "file"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name == "file":
                field.widget.attrs.setdefault("class", "block w-full text-sm text-gray-900 border border-gray-300 rounded-md cursor-pointer bg-gray-50 focus:outline-none")
            else:
                field.widget.attrs.setdefault("class", "block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 shadow-sm outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 sm:text-sm sm:leading-6")

from .models import School

class SchoolForm(forms.ModelForm):
    class Meta:
        model = School
        fields = ["name", "school_code", "teacher_code", "admin_code"]
        labels = {
            "name": "School Name",
            "school_code": "Student Code",
            "teacher_code": "Teacher Code",
            "admin_code": "Academic Admin Code",
        }
        help_texts = {
            "school_code": "Students use this code to self-register.",
            "teacher_code": "Teachers / Instructors use this code to self-register.",
            "admin_code": "Academic Admins use this code to self-register.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 shadow-sm outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 sm:text-sm sm:leading-6")

class UserCreationForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=[
        (Profile.Role.STUDENT, "Student"),
        (Profile.Role.INSTRUCTOR, "Teacher/Instructor"),
        (Profile.Role.ACADEMIC_ADMIN, "Academic Admin"),
    ])
    school = forms.ModelChoiceField(queryset=School.objects.all(), required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 shadow-sm outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 sm:text-sm sm:leading-6")

class SignupForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    school_code = forms.CharField(max_length=64, label="School / Access Code")
    role = forms.ChoiceField(choices=[
        (Profile.Role.STUDENT, "Student"),
        (Profile.Role.INSTRUCTOR, "Teacher/Instructor"),
        (Profile.Role.ACADEMIC_ADMIN, "Academic Admin"),
    ])

    def clean(self):
        cleaned_data = super().clean()
        code = cleaned_data.get('school_code')
        role = cleaned_data.get('role')
        if code and role:
            if role == Profile.Role.STUDENT:
                if not School.objects.filter(school_code=code).exists():
                    self.add_error('school_code', "Invalid student code. Please check with your administrator.")
            elif role == Profile.Role.INSTRUCTOR:
                if not School.objects.filter(teacher_code=code).exists():
                    self.add_error('school_code', "Invalid teacher code. Please check with your administrator.")
            elif role == Profile.Role.ACADEMIC_ADMIN:
                if not School.objects.filter(admin_code=code).exists():
                    self.add_error('school_code', "Invalid academic admin code. Please check with your administrator.")
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 shadow-sm outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 sm:text-sm sm:leading-6")
