
from django.contrib.auth import get_user_model, login
from .forms import SchoolForm, UserCreationForm, SignupForm
from .models import School

def _can_manage_platform(user):
    return user.is_authenticated and hasattr(user, 'profile') and user.profile.role == Profile.Role.PLATFORM_ADMIN

def signup_view(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            school_code = form.cleaned_data["school_code"]
            school = School.objects.get(school_code=school_code)
            
            User = get_user_model()
            # In a real app we'd validate email uniqueness
            if User.objects.filter(email=form.cleaned_data["email"]).exists():
                messages.error(request, "Email already in use.")
                return render(request, "registration/signup.html", {"form": form})
                
            user = User.objects.create_user(
                username=form.cleaned_data["email"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
            )
            Profile.objects.create(
                user=user,
                role=form.cleaned_data["role"],
                school=school
            )
            login(request, user)
            messages.success(request, f"Welcome! You have joined {school.name}.")
            return redirect("academics:dashboard")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form})

@login_required
def platform_admin_dashboard(request):
    if not _can_manage_platform(request.user):
        raise PermissionDenied
        
    schools = School.objects.all().order_by("-created_at")
    User = get_user_model()
    users = User.objects.filter(profile__isnull=False).select_related("profile", "profile__school").order_by("-date_joined")
    
    return render(request, "academics/dashboards/platform_admin.html", {
        "schools": schools,
        "users": users
    })

@login_required
def create_school(request):
    if not _can_manage_platform(request.user):
        raise PermissionDenied
        
    if request.method == "POST":
        form = SchoolForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "School created successfully.")
            return redirect("academics:platform_admin_dashboard")
    else:
        form = SchoolForm()
    return render(request, "academics/platform_admin/create_school.html", {"form": form})

@login_required
def create_user(request):
    if not _can_manage_platform(request.user):
        raise PermissionDenied
        
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            User = get_user_model()
            if User.objects.filter(email=form.cleaned_data["email"]).exists():
                messages.error(request, "Email already in use.")
            else:
                user = User.objects.create_user(
                    username=form.cleaned_data["email"],
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password"],
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                )
                Profile.objects.create(
                    user=user,
                    role=form.cleaned_data["role"],
                    school=form.cleaned_data["school"]
                )
                messages.success(request, f"Account created for {user.email}.")
                return redirect("academics:platform_admin_dashboard")
    else:
        form = UserCreationForm()
    return render(request, "academics/platform_admin/create_user.html", {"form": form})
