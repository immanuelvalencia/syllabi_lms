import os
import sys
import random
import json
from decimal import Decimal
import django

# Bootstrap Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from academics.models import (
    Course, CourseSection, SectionEnrollment, ActivitySection, 
    Assignment, Question, Submission, Enrollment, Profile
)

User = get_user_model()


# ─── Question Bank (20 Questions) ────────────────────────────────────────────

QUESTIONS = [
    # ── Multiple Choice (10 questions) ──
    {
        "text": "What is the SI unit of force?",
        "type": Question.QuestionType.MULTIPLE_CHOICE,
        "points": Decimal("2.00"),
        "choices": [
            {"id": "a", "label": "A", "text": "Joule"},
            {"id": "b", "label": "B", "text": "Newton"},
            {"id": "c", "label": "C", "text": "Watt"},
            {"id": "d", "label": "D", "text": "Pascal"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "Which of the following are vector quantities?",
        "type": Question.QuestionType.MULTIPLE_CHOICE,
        "points": Decimal("2.00"),
        "choices": [
            {"id": "a", "label": "A", "text": "Velocity"},
            {"id": "b", "label": "B", "text": "Speed"},
            {"id": "c", "label": "C", "text": "Acceleration"},
            {"id": "d", "label": "D", "text": "Mass"},
        ],
        "correct_answers": ["a", "c"],
    },
    {
        "text": "What does Newton's second law relate?",
        "type": Question.QuestionType.MULTIPLE_CHOICE,
        "points": Decimal("2.00"),
        "choices": [
            {"id": "a", "label": "A", "text": "Mass and velocity"},
            {"id": "b", "label": "B", "text": "Force, mass, and acceleration"},
            {"id": "c", "label": "C", "text": "Energy and momentum"},
            {"id": "d", "label": "D", "text": "Gravity and distance"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "Which type of energy does a compressed spring store?",
        "type": Question.QuestionType.MULTIPLE_CHOICE,
        "points": Decimal("2.00"),
        "choices": [
            {"id": "a", "label": "A", "text": "Kinetic energy"},
            {"id": "b", "label": "B", "text": "Thermal energy"},
            {"id": "c", "label": "C", "text": "Elastic potential energy"},
            {"id": "d", "label": "D", "text": "Chemical energy"},
        ],
        "correct_answers": ["c"],
    },
    {
        "text": "What is the acceleration due to gravity on Earth's surface (approximately)?",
        "type": Question.QuestionType.MULTIPLE_CHOICE,
        "points": Decimal("2.00"),
        "choices": [
            {"id": "a", "label": "A", "text": "3.8 m/s²"},
            {"id": "b", "label": "B", "text": "9.8 m/s²"},
            {"id": "c", "label": "C", "text": "15.2 m/s²"},
            {"id": "d", "label": "D", "text": "6.7 m/s²"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "Which law states that every action has an equal and opposite reaction?",
        "type": Question.QuestionType.MULTIPLE_CHOICE,
        "points": Decimal("2.00"),
        "choices": [
            {"id": "a", "label": "A", "text": "Newton's First Law"},
            {"id": "b", "label": "B", "text": "Newton's Second Law"},
            {"id": "c", "label": "C", "text": "Newton's Third Law"},
            {"id": "d", "label": "D", "text": "Law of Conservation of Energy"},
        ],
        "correct_answers": ["c"],
    },
    {
        "text": "What is the SI unit of work?",
        "type": Question.QuestionType.MULTIPLE_CHOICE,
        "points": Decimal("2.00"),
        "choices": [
            {"id": "a", "label": "A", "text": "Newton"},
            {"id": "b", "label": "B", "text": "Joule"},
            {"id": "c", "label": "C", "text": "Watt"},
            {"id": "d", "label": "D", "text": "Pascal"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "A freely falling object experiences which type of motion?",
        "type": Question.QuestionType.MULTIPLE_CHOICE,
        "points": Decimal("2.00"),
        "choices": [
            {"id": "a", "label": "A", "text": "Uniform velocity"},
            {"id": "b", "label": "B", "text": "Uniform acceleration"},
            {"id": "c", "label": "C", "text": "Non-uniform acceleration"},
            {"id": "d", "label": "D", "text": "Zero acceleration"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "Which quantity is conserved in an elastic collision?",
        "type": Question.QuestionType.MULTIPLE_CHOICE,
        "points": Decimal("2.00"),
        "choices": [
            {"id": "a", "label": "A", "text": "Only momentum"},
            {"id": "b", "label": "B", "text": "Only kinetic energy"},
            {"id": "c", "label": "C", "text": "Both momentum and kinetic energy"},
            {"id": "d", "label": "D", "text": "Neither"},
        ],
        "correct_answers": ["c"],
    },
    {
        "text": "What is the SI unit of power?",
        "type": Question.QuestionType.MULTIPLE_CHOICE,
        "points": Decimal("2.00"),
        "choices": [
            {"id": "a", "label": "A", "text": "Joule"},
            {"id": "b", "label": "B", "text": "Newton"},
            {"id": "c", "label": "C", "text": "Watt"},
            {"id": "d", "label": "D", "text": "Hertz"},
        ],
        "correct_answers": ["c"],
    },
    # ── True / False (5 questions) ──
    {
        "text": "An object in motion will remain in motion unless acted upon by an external force.",
        "type": Question.QuestionType.TRUE_FALSE,
        "points": Decimal("1.00"),
        "correct_answer": "True",
    },
    {
        "text": "Acceleration is the rate of change of displacement.",
        "type": Question.QuestionType.TRUE_FALSE,
        "points": Decimal("1.00"),
        "correct_answer": "False",
    },
    {
        "text": "Weight and mass are the same physical quantity.",
        "type": Question.QuestionType.TRUE_FALSE,
        "points": Decimal("1.00"),
        "correct_answer": "False",
    },
    {
        "text": "The net force on an object moving at constant velocity is zero.",
        "type": Question.QuestionType.TRUE_FALSE,
        "points": Decimal("1.00"),
        "correct_answer": "True",
    },
    {
        "text": "Potential energy depends on an object's velocity.",
        "type": Question.QuestionType.TRUE_FALSE,
        "points": Decimal("1.00"),
        "correct_answer": "False",
    },
    # ── Numeric (3 questions) ──
    {
        "text": "A car travels 100 meters in 5 seconds. What is its average speed in m/s?",
        "type": Question.QuestionType.NUMBER,
        "points": Decimal("3.00"),
        "correct_answer": "20",
        "answer_settings": {"accepted_range": {"min": "19.9", "max": "20.1"}},
    },
    {
        "text": "What is the kinetic energy (in Joules) of a 2 kg object moving at 3 m/s? (KE = ½mv²)",
        "type": Question.QuestionType.NUMBER,
        "points": Decimal("3.00"),
        "correct_answer": "9",
        "answer_settings": {"accepted_range": {"min": "8.9", "max": "9.1"}},
    },
    {
        "text": "A 5 N force is applied over 4 meters. How much work (in Joules) is done?",
        "type": Question.QuestionType.NUMBER,
        "points": Decimal("3.00"),
        "correct_answer": "20",
        "answer_settings": {"accepted_range": {"min": "19.9", "max": "20.1"}},
    },
    # ── Text / Short Answer (2 questions) ──
    {
        "text": "State Newton's First Law of Motion in your own words.",
        "type": Question.QuestionType.TEXT,
        "points": Decimal("3.00"),
        "correct_answer": "",
    },
    {
        "text": "Explain the difference between distance and displacement.",
        "type": Question.QuestionType.TEXT,
        "points": Decimal("3.00"),
        "correct_answer": "",
    },
]


# ─── Random answer generators per question type ──────────────────────────────

def random_mcq_answer(q_def):
    """Return a random answer string for an MCQ question definition."""
    choice_ids = [c["id"] for c in q_def["choices"]]
    correct = q_def["correct_answers"]

    if len(correct) > 1:
        # Multi-select: sometimes pick the correct combo, sometimes a random subset
        options = [
            ",".join(correct),                               # correct
            random.choice(choice_ids),                       # single random
            ",".join(random.sample(choice_ids, k=2)),        # random pair
        ]
    else:
        options = choice_ids  # single-select: pick any one

    return random.choice(options)


def random_tf_answer(_q_def):
    return random.choice(["True", "False"])


def random_number_answer(q_def):
    correct = float(q_def["correct_answer"])
    settings = q_def.get("answer_settings", {})
    rng = settings.get("accepted_range", {})
    lo = float(rng.get("min", correct - 5))
    hi = float(rng.get("max", correct + 5))
    # 50 % chance of correct-ish value, 50 % of something farther off
    if random.random() < 0.5:
        return str(round(random.uniform(lo, hi), 2))
    else:
        return str(round(random.uniform(correct - 10, correct + 10), 2))


TEXT_RESPONSES = {
    "State Newton's First Law of Motion in your own words.": [
        "An object at rest stays at rest and an object in motion stays in motion unless acted on by a net force.",
        "If nothing pushes or pulls on something, it keeps doing what it was already doing.",
        "Things don't change their motion without a force.",
        "Newton's first law says objects resist changes in their state of motion.",
        "I'm not sure about this one.",
    ],
    "Explain the difference between distance and displacement.": [
        "Distance is scalar total path length while displacement is vector straight-line difference between start and end.",
        "Distance is how far you travel, displacement is how far you end up from where you started.",
        "Distance has no direction, displacement does.",
        "They are both measurements of length but displacement includes direction.",
        "I think they are the same thing?",
    ],
}


def random_text_answer(q_def):
    return random.choice(TEXT_RESPONSES.get(q_def["text"], ["No answer provided."]))


ANSWER_GENERATORS = {
    Question.QuestionType.MULTIPLE_CHOICE: random_mcq_answer,
    Question.QuestionType.TRUE_FALSE: random_tf_answer,
    Question.QuestionType.NUMBER: random_number_answer,
    Question.QuestionType.TEXT: random_text_answer,
}


# ─── Score helpers ────────────────────────────────────────────────────────────

def score_answer(q_def, question_obj, answer_str):
    """Return the earned points (Decimal) for a single answer."""
    qtype = q_def["type"]

    if qtype == Question.QuestionType.MULTIPLE_CHOICE:
        student_set = set(answer_str.split(","))
        correct_set = set(q_def["correct_answers"])
        if student_set == correct_set:
            return question_obj.points
        return Decimal("0.00")

    if qtype == Question.QuestionType.TRUE_FALSE:
        if answer_str.lower() == q_def["correct_answer"].lower():
            return question_obj.points
        return Decimal("0.00")

    if qtype == Question.QuestionType.NUMBER:
        try:
            val = float(answer_str)
            settings = q_def.get("answer_settings", {})
            rng = settings.get("accepted_range", {})
            lo = float(rng.get("min", float(q_def["correct_answer"]) - 0.1))
            hi = float(rng.get("max", float(q_def["correct_answer"]) + 0.1))
            if lo <= val <= hi:
                return question_obj.points
        except (ValueError, TypeError):
            pass
        return Decimal("0.00")

    # TEXT – not auto-graded
    return Decimal("0.00")


# ─── Main ─────────────────────────────────────────────────────────────────────

def run():
    # 1. Get or create a course
    course = Course.objects.filter(code="phys1").first()
    if not course:
        course = Course.objects.first()
    if not course:
        teacher, _ = User.objects.get_or_create(
            username="teacher_dummy",
            email="teacher@example.com",
            defaults={"first_name": "Dummy", "last_name": "Instructor"},
        )
        profile, _ = Profile.objects.get_or_create(user=teacher)
        profile.role = Profile.Role.INSTRUCTOR
        profile.save()

        course = Course.objects.create(
            title="General Physics I",
            code="phys1",
            instructor=teacher,
        )
        print(f"Created Course: {course}")
    else:
        print(f"Using Course: {course}")

    # 2. Get or create CourseSection
    section = course.sections.first()
    if not section:
        section = CourseSection.objects.create(course=course, name="Section 1", order=1)
        print(f"Created Course Section: {section}")
    else:
        print(f"Using Course Section: {section}")

    # 3. Get or create ActivitySection
    activity_section, _ = ActivitySection.objects.get_or_create(
        course=course, name="Quizzes", defaults={"order": 1}
    )

    # 4. Create Quiz Assignment
    title = f"Quiz on Mechanics ({section.name}) - {timezone.now().strftime('%Y-%m-%d %H:%M')}"
    assignment = Assignment.objects.create(
        course=course,
        course_section=section,
        activity_section=activity_section,
        activity_type=Assignment.ActivityType.QUIZ,
        title=title,
        max_score=Decimal("0.00"),  # will be recalculated
        instructor=course.instructor,
        due_at=timezone.now() + timezone.timedelta(days=7),
    )
    print(f"Created Quiz Assignment: {assignment}")

    # 5. Create 20 Questions
    question_objects = []
    for idx, q_def in enumerate(QUESTIONS, start=1):
        kwargs = {
            "assignment": assignment,
            "text": q_def["text"],
            "question_type": q_def["type"],
            "points": q_def["points"],
            "order": idx,
        }
        if q_def["type"] == Question.QuestionType.MULTIPLE_CHOICE:
            kwargs["choices"] = q_def["choices"]
            kwargs["correct_answers"] = q_def["correct_answers"]
        elif q_def["type"] == Question.QuestionType.TRUE_FALSE:
            kwargs["correct_answer"] = q_def["correct_answer"]
        elif q_def["type"] == Question.QuestionType.NUMBER:
            kwargs["correct_answer"] = q_def["correct_answer"]
            kwargs["answer_settings"] = q_def.get("answer_settings", {})
        # TEXT questions have no correct_answer

        question_objects.append(Question.objects.create(**kwargs))

    assignment.max_score = sum(q.points for q in question_objects)
    assignment.save()
    print(f"Created {len(question_objects)} questions. Total points: {assignment.max_score}")

    # 6. Get enrolled students in the section
    section_enrollments = SectionEnrollment.objects.filter(section=section)
    students = [se.student for se in section_enrollments]

    if not students:
        print(f"No students enrolled in {section.name}. Creating 5 dummy students...")
        for idx in range(1, 6):
            username = f"student_dummy_{idx}"
            email = f"student_{idx}@example.com"
            student, _ = User.objects.get_or_create(
                username=username,
                email=email,
                defaults={"first_name": "Student", "last_name": str(idx)},
            )
            profile, _ = Profile.objects.get_or_create(user=student)
            profile.role = Profile.Role.STUDENT
            profile.save()
            Enrollment.objects.get_or_create(student=student, course=course)
            SectionEnrollment.objects.get_or_create(student=student, section=section)
            students.append(student)

    # 7. Generate random submissions for every student
    for student in students:
        answers = {}
        earned_points = Decimal("0.00")

        for q_def, q_obj in zip(QUESTIONS, question_objects):
            gen = ANSWER_GENERATORS[q_def["type"]]
            ans = gen(q_def)
            answers[str(q_obj.id)] = ans
            earned_points += score_answer(q_def, q_obj, ans)

        submission_content = json.dumps({
            "answers": answers,
            "student_notes": f"Submitted by test script for {student.username}.",
        })

        # Randomly decide graded vs awaiting
        is_graded = random.choice([True, False])
        defaults = {
            "content": submission_content,
            "attachment_url": "",
        }
        if is_graded:
            defaults["score"] = earned_points
            defaults["graded_at"] = timezone.now()
            defaults["feedback"] = "Auto-graded by test script."
        else:
            defaults["score"] = None
            defaults["graded_at"] = None
            defaults["feedback"] = ""

        sub, _ = Submission.objects.update_or_create(
            assignment=assignment,
            student=student,
            defaults=defaults,
        )
        status = f"Graded {sub.score}/{assignment.max_score}" if is_graded else "Awaiting grading"
        print(f"  {student.username}: {status}")

    print(f"\nDone! Quiz with {len(question_objects)} questions populated for "
          f"{section.name} with {len(students)} student submissions.")


if __name__ == "__main__":
    run()
