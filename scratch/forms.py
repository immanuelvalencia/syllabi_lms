
from .models import School

class SchoolForm(forms.ModelForm):
    class Meta:
        model = School
        fields = ["name", "school_code"]
        labels = {
            "name": "School Name",
            "school_code": "School Code",
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update(
                {
                    "class": "mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                }
            )

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
            field.widget.attrs.update(
                {
                    "class": "mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                }
            )

class SignupForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    school_code = forms.CharField(max_length=64)
    role = forms.ChoiceField(choices=[
        (Profile.Role.STUDENT, "Student"),
        (Profile.Role.INSTRUCTOR, "Teacher/Instructor"),
    ])

    def clean_school_code(self):
        code = self.cleaned_data['school_code']
        if not School.objects.filter(school_code=code).exists():
            raise forms.ValidationError("Invalid school code.")
        return code

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update(
                {
                    "class": "mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                }
            )
