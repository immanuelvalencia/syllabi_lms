import os
import sys
import django
import random
import string

# Set up Django environment
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from academics.models import School, Profile

def generate_random_string(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Dorothy", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell"
]

def add_mock_students():
    school, created = School.objects.get_or_create(
        name="De La Salle University",
        defaults={
            "school_code": "DLSU-" + generate_random_string(6),
            "teacher_code": "DLSU-T-" + generate_random_string(6),
            "admin_code": "DLSU-A-" + generate_random_string(6),
        }
    )
    if created:
        print(f"Created new school: {school.name}")
    else:
        print(f"Using existing school: {school.name}")

    students_to_create = 80
    grade_11_count = 40
    grade_12_count = 40

    created_count = 0
    
    # Shuffle names to get random combinations
    names_pool = []
    for f in FIRST_NAMES:
        for l in LAST_NAMES:
            names_pool.append((f, l))
    random.shuffle(names_pool)
    
    selected_names = names_pool[:students_to_create]

    for i, (first_name, last_name) in enumerate(selected_names):
        grade_level = 11 if i < grade_11_count else 12
        id_number = f"123{grade_level}{i:04d}"
        username = f"{first_name.lower()}.{last_name.lower()}{i}"
        
        # Check if user already exists
        if User.objects.filter(username=username).exists():
            continue

        user = User.objects.create_user(
            username=username,
            password="password123",
            first_name=first_name,
            last_name=last_name,
            email=f"{username}@dlsu.edu.ph"
        )

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.school = school
        profile.role = Profile.Role.STUDENT
        profile.id_number = id_number
        profile.grade_level = grade_level
        profile.save()
        
        created_count += 1

    print(f"Successfully created {created_count} mock students ({grade_11_count} in grade 11, {grade_12_count} in grade 12).")
    print(f"All students have the password: 'password123'")

if __name__ == "__main__":
    add_mock_students()
