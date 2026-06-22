"""
generate_college_algebra.py
───────────────────────────
Creates a fully-populated mock "College Algebra" course:
  • School  : De La Salle University (existing)
  • Instructor : admin (existing)
  • Sections : 3, each with 20 unique students (60 total)
  • Activities : 3 quizzes, 15 questions each (45 total questions)
  • Submissions: every student gets random answers for each activity
"""

import os
import sys
import random
import json
import string
from decimal import Decimal
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from academics.models import (
    Course, CourseSection, SectionEnrollment, ActivitySection,
    Assignment, Question, Submission, Enrollment, Profile, School,
)

User = get_user_model()

# ─────────────────────────────────────────────────────────────────────────────
# Question Banks  (3 activities × 15 questions)
# ─────────────────────────────────────────────────────────────────────────────

ACTIVITY_1_QUESTIONS = [
    # ── Activity 1: Foundations of Algebra (15 questions) ──
    # MCQ ×8
    {
        "text": "What is the value of x in the equation 2x + 6 = 14?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "2"},
            {"id": "b", "label": "B", "text": "4"},
            {"id": "c", "label": "C", "text": "6"},
            {"id": "d", "label": "D", "text": "8"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "Simplify: 3(x + 2) − 2(x − 1)",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "x + 8"},
            {"id": "b", "label": "B", "text": "x + 4"},
            {"id": "c", "label": "C", "text": "5x + 4"},
            {"id": "d", "label": "D", "text": "x + 6"},
        ],
        "correct_answers": ["a"],
    },
    {
        "text": "Which of the following is a polynomial of degree 3?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "x² + 3x + 1"},
            {"id": "b", "label": "B", "text": "2x³ − x + 7"},
            {"id": "c", "label": "C", "text": "4x⁴ + x"},
            {"id": "d", "label": "D", "text": "5x + 2"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "Factor completely: x² − 9",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "(x − 3)²"},
            {"id": "b", "label": "B", "text": "(x + 9)(x − 1)"},
            {"id": "c", "label": "C", "text": "(x + 3)(x − 3)"},
            {"id": "d", "label": "D", "text": "(x − 9)(x + 1)"},
        ],
        "correct_answers": ["c"],
    },
    {
        "text": "What is the slope of the line y = −3x + 7?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "7"},
            {"id": "b", "label": "B", "text": "−3"},
            {"id": "c", "label": "C", "text": "3"},
            {"id": "d", "label": "D", "text": "−7"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "Which property is demonstrated by a(b + c) = ab + ac?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "Commutative property"},
            {"id": "b", "label": "B", "text": "Associative property"},
            {"id": "c", "label": "C", "text": "Distributive property"},
            {"id": "d", "label": "D", "text": "Identity property"},
        ],
        "correct_answers": ["c"],
    },
    {
        "text": "Evaluate: |−5| + |3|",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "−2"},
            {"id": "b", "label": "B", "text": "2"},
            {"id": "c", "label": "C", "text": "8"},
            {"id": "d", "label": "D", "text": "−8"},
        ],
        "correct_answers": ["c"],
    },
    {
        "text": "Which of the following is a rational number?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "√2"},
            {"id": "b", "label": "B", "text": "π"},
            {"id": "c", "label": "C", "text": "3/4"},
            {"id": "d", "label": "D", "text": "√5"},
        ],
        "correct_answers": ["c"],
    },
    # T/F ×4
    {
        "text": "The set of integers is a subset of the set of rational numbers.",
        "type": "true_false", "points": "1.00",
        "correct_answer": "True",
    },
    {
        "text": "Every real number is a complex number.",
        "type": "true_false", "points": "1.00",
        "correct_answer": "True",
    },
    {
        "text": "The product of two negative numbers is always negative.",
        "type": "true_false", "points": "1.00",
        "correct_answer": "False",
    },
    {
        "text": "Zero is a natural number.",
        "type": "true_false", "points": "1.00",
        "correct_answer": "False",
    },
    # Number ×2
    {
        "text": "Solve for x: 5x − 3 = 22. Enter the value of x.",
        "type": "number", "points": "3.00",
        "correct_answer": "5",
        "answer_settings": {"accepted_range": {"min": "4.9", "max": "5.1"}},
    },
    {
        "text": "Evaluate: (−2)³ + 4². Enter the result.",
        "type": "number", "points": "3.00",
        "correct_answer": "8",
        "answer_settings": {"accepted_range": {"min": "7.9", "max": "8.1"}},
    },
    # Text ×1
    {
        "text": "In your own words, explain what a variable represents in an algebraic expression.",
        "type": "text", "points": "3.00",
        "correct_answer": "",
    },
]

ACTIVITY_2_QUESTIONS = [
    # ── Activity 2: Equations & Inequalities (15 questions) ──
    # MCQ ×8
    {
        "text": "Solve: 3x + 5 = 20. What is the value of x?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "3"},
            {"id": "b", "label": "B", "text": "5"},
            {"id": "c", "label": "C", "text": "7"},
            {"id": "d", "label": "D", "text": "15"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "Which inequality represents 'x is at least 5'?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "x > 5"},
            {"id": "b", "label": "B", "text": "x < 5"},
            {"id": "c", "label": "C", "text": "x ≥ 5"},
            {"id": "d", "label": "D", "text": "x ≤ 5"},
        ],
        "correct_answers": ["c"],
    },
    {
        "text": "The solution set of |x| < 3 is:",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "x < 3"},
            {"id": "b", "label": "B", "text": "−3 < x < 3"},
            {"id": "c", "label": "C", "text": "x > −3"},
            {"id": "d", "label": "D", "text": "x < −3 or x > 3"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "How many solutions does the equation x² = −4 have in the real numbers?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "0"},
            {"id": "b", "label": "B", "text": "1"},
            {"id": "c", "label": "C", "text": "2"},
            {"id": "d", "label": "D", "text": "Infinite"},
        ],
        "correct_answers": ["a"],
    },
    {
        "text": "Which method can be used to solve all quadratic equations?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "Factoring"},
            {"id": "b", "label": "B", "text": "Completing the square"},
            {"id": "c", "label": "C", "text": "Quadratic formula"},
            {"id": "d", "label": "D", "text": "Graphing"},
        ],
        "correct_answers": ["c"],
    },
    {
        "text": "What is the discriminant of x² + 4x + 4 = 0?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "0"},
            {"id": "b", "label": "B", "text": "4"},
            {"id": "c", "label": "C", "text": "8"},
            {"id": "d", "label": "D", "text": "−4"},
        ],
        "correct_answers": ["a"],
    },
    {
        "text": "If 2(x − 3) > 4, then x is:",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "x > 5"},
            {"id": "b", "label": "B", "text": "x > 3"},
            {"id": "c", "label": "C", "text": "x > 7"},
            {"id": "d", "label": "D", "text": "x > 1"},
        ],
        "correct_answers": ["a"],
    },
    {
        "text": "Select all that are solutions to x² − 5x + 6 = 0.",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "1"},
            {"id": "b", "label": "B", "text": "2"},
            {"id": "c", "label": "C", "text": "3"},
            {"id": "d", "label": "D", "text": "6"},
        ],
        "correct_answers": ["b", "c"],
    },
    # T/F ×4
    {
        "text": "A linear equation in one variable has exactly one solution.",
        "type": "true_false", "points": "1.00",
        "correct_answer": "True",
    },
    {
        "text": "Multiplying both sides of an inequality by a negative number reverses the inequality sign.",
        "type": "true_false", "points": "1.00",
        "correct_answer": "True",
    },
    {
        "text": "The equation x² + 1 = 0 has real solutions.",
        "type": "true_false", "points": "1.00",
        "correct_answer": "False",
    },
    {
        "text": "An absolute value expression can be negative.",
        "type": "true_false", "points": "1.00",
        "correct_answer": "False",
    },
    # Number ×2
    {
        "text": "Using the quadratic formula, find the positive root of x² − 7x + 10 = 0.",
        "type": "number", "points": "3.00",
        "correct_answer": "5",
        "answer_settings": {"accepted_range": {"min": "4.9", "max": "5.1"}},
    },
    {
        "text": "Solve: |2x − 6| = 10. Enter the larger value of x.",
        "type": "number", "points": "3.00",
        "correct_answer": "8",
        "answer_settings": {"accepted_range": {"min": "7.9", "max": "8.1"}},
    },
    # Text ×1
    {
        "text": "Describe the difference between a conditional equation and an identity. Provide an example of each.",
        "type": "text", "points": "3.00",
        "correct_answer": "",
    },
]

ACTIVITY_3_QUESTIONS = [
    # ── Activity 3: Functions & Graphing (15 questions) ──
    # MCQ ×8
    {
        "text": "Which of the following represents a function?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "x² + y² = 1"},
            {"id": "b", "label": "B", "text": "y = 2x + 3"},
            {"id": "c", "label": "C", "text": "x = y²"},
            {"id": "d", "label": "D", "text": "x + y = |y|"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "What is the domain of f(x) = 1/(x − 2)?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "All real numbers"},
            {"id": "b", "label": "B", "text": "x ≠ 0"},
            {"id": "c", "label": "C", "text": "x ≠ 2"},
            {"id": "d", "label": "D", "text": "x > 2"},
        ],
        "correct_answers": ["c"],
    },
    {
        "text": "If f(x) = 3x − 1, what is f(4)?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "11"},
            {"id": "b", "label": "B", "text": "12"},
            {"id": "c", "label": "C", "text": "7"},
            {"id": "d", "label": "D", "text": "13"},
        ],
        "correct_answers": ["a"],
    },
    {
        "text": "The graph of y = x² is a:",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "Straight line"},
            {"id": "b", "label": "B", "text": "Parabola"},
            {"id": "c", "label": "C", "text": "Circle"},
            {"id": "d", "label": "D", "text": "Hyperbola"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "What is the range of f(x) = x²?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "All real numbers"},
            {"id": "b", "label": "B", "text": "y ≥ 0"},
            {"id": "c", "label": "C", "text": "y > 0"},
            {"id": "d", "label": "D", "text": "y ≤ 0"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "What transformation does y = f(x) + 3 apply to the graph of y = f(x)?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "Shift 3 units right"},
            {"id": "b", "label": "B", "text": "Shift 3 units left"},
            {"id": "c", "label": "C", "text": "Shift 3 units up"},
            {"id": "d", "label": "D", "text": "Shift 3 units down"},
        ],
        "correct_answers": ["c"],
    },
    {
        "text": "The vertical line test is used to determine whether a graph represents:",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "A relation"},
            {"id": "b", "label": "B", "text": "A function"},
            {"id": "c", "label": "C", "text": "A polynomial"},
            {"id": "d", "label": "D", "text": "A linear equation"},
        ],
        "correct_answers": ["b"],
    },
    {
        "text": "Which pair of functions are inverses of each other?",
        "type": "multiple_choice", "points": "2.00",
        "choices": [
            {"id": "a", "label": "A", "text": "f(x) = 2x and g(x) = x/2"},
            {"id": "b", "label": "B", "text": "f(x) = x + 1 and g(x) = x + 1"},
            {"id": "c", "label": "C", "text": "f(x) = x² and g(x) = 2x"},
            {"id": "d", "label": "D", "text": "f(x) = x³ and g(x) = 3x"},
        ],
        "correct_answers": ["a"],
    },
    # T/F ×4
    {
        "text": "Every function is a relation, but not every relation is a function.",
        "type": "true_false", "points": "1.00",
        "correct_answer": "True",
    },
    {
        "text": "The graph of a linear function is always a straight line.",
        "type": "true_false", "points": "1.00",
        "correct_answer": "True",
    },
    {
        "text": "A quadratic function can have at most three x-intercepts.",
        "type": "true_false", "points": "1.00",
        "correct_answer": "False",
    },
    {
        "text": "The function f(x) = √x is defined for all real numbers.",
        "type": "true_false", "points": "1.00",
        "correct_answer": "False",
    },
    # Number ×2
    {
        "text": "If f(x) = 2x² − 3x + 1, evaluate f(3). Enter the result.",
        "type": "number", "points": "3.00",
        "correct_answer": "10",
        "answer_settings": {"accepted_range": {"min": "9.9", "max": "10.1"}},
    },
    {
        "text": "Find the y-intercept of y = 4x − 12. Enter the y-value.",
        "type": "number", "points": "3.00",
        "correct_answer": "-12",
        "answer_settings": {"accepted_range": {"min": "-12.1", "max": "-11.9"}},
    },
    # Text ×1
    {
        "text": "Explain how the vertical line test determines whether a graph represents a function.",
        "type": "text", "points": "3.00",
        "correct_answer": "",
    },
]

ALL_ACTIVITIES = [
    {
        "title": "Quiz 1: Foundations of Algebra",
        "instructions": (
            "This quiz covers the foundational concepts of College Algebra including "
            "real numbers, algebraic expressions, order of operations, and basic equation solving. "
            "Answer all 15 questions. Multiple choice questions are worth 2 points each, "
            "True/False questions are worth 1 point each, numeric questions are worth 3 points each, "
            "and the short-answer question is worth 3 points."
        ),
        "questions": ACTIVITY_1_QUESTIONS,
    },
    {
        "title": "Quiz 2: Equations & Inequalities",
        "instructions": (
            "This quiz assesses your understanding of linear and quadratic equations, "
            "inequalities, absolute value equations, and the quadratic formula. "
            "Read each question carefully. Show your work for numeric answers."
        ),
        "questions": ACTIVITY_2_QUESTIONS,
    },
    {
        "title": "Quiz 3: Functions & Graphing",
        "instructions": (
            "This quiz covers the concept of functions, function notation, domain and range, "
            "graphing transformations, the vertical line test, and inverse functions. "
            "Answer all 15 questions."
        ),
        "questions": ACTIVITY_3_QUESTIONS,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Student name pools (Filipino-themed for DLSU context)
# ─────────────────────────────────────────────────────────────────────────────

FIRST_NAMES = [
    "Miguel", "Sofia", "Andrei", "Isabela", "Carlos", "Mariana", "Joaquin", "Gabriela",
    "Rafael", "Patricia", "Lorenzo", "Angela", "Marco", "Victoria", "Diego", "Camilla",
    "Enrique", "Daniela", "Sebastian", "Francesca", "Luis", "Elena", "Antonio", "Beatrice",
    "Paolo", "Christine", "Manuel", "Nicole", "Eduardo", "Cassandra", "Fernando", "Samantha",
    "Ricardo", "Bianca", "Jose", "Kristen", "Alejandro", "Monique", "Vincent", "Janine",
    "Adrian", "Catherine", "Roberto", "Veronica", "Ramon", "Michelle", "Gabriel", "Theresa",
    "Dominic", "Stephanie", "Francis", "Pauline", "Christian", "Angelica", "Benedict", "Clarissa",
    "Emilio", "Trisha", "Nathaniel", "Leanne",
]

LAST_NAMES = [
    "Reyes", "Santos", "Cruz", "Garcia", "Bautista", "Del Rosario", "Mendoza", "Torres",
    "Gonzales", "Lopez", "Martinez", "Villanueva", "Ramos", "Flores", "De Leon", "Aquino",
    "Pascual", "Navarro", "Rivera", "Castillo", "Fernandez", "Aguilar", "Domingo", "Hernandez",
    "Salvador", "Padilla", "Manalo", "Soriano", "De Guzman", "Lim", "Tan", "Chua",
    "Ong", "Co", "Sy", "Ang", "Yu", "Cheng", "Yap", "Lee",
    "Velasco", "Perez", "Salazar", "Espinosa", "Villareal", "Magno", "Robles", "Serrano",
    "Galang", "Tolentino", "Ignacio", "Mercado", "Lagunzad", "Dimaculangan", "Buenaventura", "Evangelista",
    "Alcantara", "Palma", "Ilagan", "Roxas",
]

SECTION_NAMES = ["Section A", "Section B", "Section C"]
SECTION_SCHEDULES = [
    {"schedule_title": "MWF 8:00 AM – 9:00 AM", "meeting_days": "Mon, Wed, Fri",
     "start_time": "08:00", "end_time": "09:00", "location": "Gokongwei Hall Rm 201"},
    {"schedule_title": "TTh 10:30 AM – 12:00 PM", "meeting_days": "Tue, Thu",
     "start_time": "10:30", "end_time": "12:00", "location": "La Salle Hall Rm 305"},
    {"schedule_title": "MWF 1:00 PM – 2:00 PM", "meeting_days": "Mon, Wed, Fri",
     "start_time": "13:00", "end_time": "14:00", "location": "Andrew Hall Rm 102"},
]


# ─────────────────────────────────────────────────────────────────────────────
# Answer generators
# ─────────────────────────────────────────────────────────────────────────────

TEXT_POOL = {
    "In your own words, explain what a variable represents in an algebraic expression.": [
        "A variable is a symbol, usually a letter, that stands for an unknown or changeable value in a mathematical expression.",
        "Variables represent quantities that can change or that we need to find.",
        "It is a placeholder for a number we don't know yet.",
        "A variable is like a container that holds a number which may vary.",
        "I'm not entirely sure but I think it's a letter used in math.",
    ],
    "Describe the difference between a conditional equation and an identity. Provide an example of each.": [
        "A conditional equation is true only for certain values (e.g., 2x = 6 is only true when x=3), while an identity is true for all values (e.g., x + x = 2x).",
        "Conditional equations have limited solutions. Identities are always true. Example: x+1=3 vs. a+b=b+a.",
        "An identity holds for every value of the variable, like (a+b)²=a²+2ab+b². A conditional equation like x=5 only works for one value.",
        "I think conditional means it depends on the value and identity means it's always true.",
        "Not sure about this topic.",
    ],
    "Explain how the vertical line test determines whether a graph represents a function.": [
        "If any vertical line crosses the graph at more than one point, the graph does not represent a function because a function assigns exactly one output for each input.",
        "You draw vertical lines through the graph. If a vertical line hits the graph twice, it fails the test and is not a function.",
        "The vertical line test checks if each x-value maps to only one y-value. Multiple intersections mean it's not a function.",
        "A function must pass the vertical line test, meaning no vertical line touches the curve more than once.",
        "I remember something about drawing lines but I'm not sure of the details.",
    ],
}


def gen_mcq(q_def):
    choice_ids = [c["id"] for c in q_def["choices"]]
    correct = q_def["correct_answers"]
    if len(correct) > 1:
        opts = [",".join(correct), random.choice(choice_ids), ",".join(random.sample(choice_ids, k=2))]
    else:
        opts = choice_ids
    return random.choice(opts)


def gen_tf(_q):
    return random.choice(["True", "False"])


def gen_number(q_def):
    correct = float(q_def["correct_answer"])
    rng = q_def.get("answer_settings", {}).get("accepted_range", {})
    lo = float(rng.get("min", correct - 5))
    hi = float(rng.get("max", correct + 5))
    if random.random() < 0.5:
        return str(round(random.uniform(lo, hi), 2))
    else:
        return str(round(random.uniform(correct - 10, correct + 10), 2))


def gen_text(q_def):
    return random.choice(TEXT_POOL.get(q_def["text"], ["I'm not sure about this."]))


GENERATORS = {
    "multiple_choice": gen_mcq,
    "true_false": gen_tf,
    "number": gen_number,
    "text": gen_text,
}


def score_answer(q_def, q_obj, answer_str):
    qtype = q_def["type"]
    if qtype == "multiple_choice":
        if set(answer_str.split(",")) == set(q_def["correct_answers"]):
            return q_obj.points
        return Decimal("0.00")
    if qtype == "true_false":
        if answer_str.lower() == q_def["correct_answer"].lower():
            return q_obj.points
        return Decimal("0.00")
    if qtype == "number":
        try:
            val = float(answer_str)
            rng = q_def.get("answer_settings", {}).get("accepted_range", {})
            lo = float(rng.get("min", float(q_def["correct_answer"]) - 0.1))
            hi = float(rng.get("max", float(q_def["correct_answer"]) + 0.1))
            if lo <= val <= hi:
                return q_obj.points
        except (ValueError, TypeError):
            pass
        return Decimal("0.00")
    return Decimal("0.00")  # text not auto-graded


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run():
    # ── School ──
    school = School.objects.filter(name__icontains="De La Salle").first()
    if not school:
        school = School.objects.create(
            name="De La Salle University",
            school_code="DLSUSTUDENT",
        )
        print(f"Created School: {school}")
    else:
        print(f"Using School: {school}")

    # ── Instructor (admin) ──
    instructor = User.objects.filter(username="admin").first()
    if not instructor:
        print("ERROR: No 'admin' user found. Create it first.")
        return
    print(f"Instructor: {instructor.get_full_name()} ({instructor.username})")

    # ── Course ──
    course, created = Course.objects.get_or_create(
        code="COALGE",
        defaults={
            "title": "College Algebra",
            "slug": "coalge",
            "description": (
                "A comprehensive course in College Algebra covering the real number system, "
                "algebraic expressions, equations and inequalities, functions and their graphs, "
                "polynomial and rational functions, exponential and logarithmic functions, "
                "and systems of equations. Designed for first-year college students."
            ),
            "instructor": instructor,
            "school": school,
            "department": "Mathematics Department",
            "school_year": "2025-2026",
            "grade_level": "College - 1st Year",
            "is_active": True,
            "start_date": timezone.now().date(),
            "end_date": (timezone.now() + timezone.timedelta(days=120)).date(),
        },
    )
    if created:
        print(f"Created Course: {course}")
    else:
        print(f"Using existing Course: {course}")

    # ── Activity Sections (grading categories) ──
    quizzes_section, _ = ActivitySection.objects.get_or_create(
        course=course, name="Quizzes",
        defaults={"order": 1, "grading_weight": Decimal("30.00")},
    )
    ActivitySection.objects.get_or_create(
        course=course, name="Assignments",
        defaults={"order": 2, "grading_weight": Decimal("20.00")},
    )
    ActivitySection.objects.get_or_create(
        course=course, name="Exams",
        defaults={"order": 3, "grading_weight": Decimal("50.00")},
    )

    # ── Sections + Students ──
    used_name_combos = set()
    name_idx = 0  # fallback counter

    def _unique_student(first_pool, last_pool):
        nonlocal name_idx
        for _ in range(200):
            fn = random.choice(first_pool)
            ln = random.choice(last_pool)
            combo = (fn, ln)
            if combo not in used_name_combos:
                used_name_combos.add(combo)
                return fn, ln
        # fallback – guaranteed unique
        name_idx += 1
        fn = random.choice(first_pool)
        ln = f"Student{name_idx}"
        used_name_combos.add((fn, ln))
        return fn, ln

    all_sections = []
    all_students_by_section = {}

    for sec_idx, sec_name in enumerate(SECTION_NAMES):
        sched = SECTION_SCHEDULES[sec_idx]
        section, sec_created = CourseSection.objects.get_or_create(
            course=course,
            name=sec_name,
            defaults={
                "schedule_title": sched["schedule_title"],
                "meeting_days": sched["meeting_days"],
                "start_time": sched["start_time"],
                "end_time": sched["end_time"],
                "location": sched["location"],
                "order": sec_idx + 1,
            },
        )
        if sec_created:
            print(f"Created Section: {section}")
        else:
            print(f"Using Section: {section}")
        all_sections.append(section)

        # Create 20 students for this section
        section_students = []
        existing_enrollments = SectionEnrollment.objects.filter(section=section).select_related("student")
        for se in existing_enrollments:
            section_students.append(se.student)

        needed = 20 - len(section_students)
        for _ in range(needed):
            fn, ln = _unique_student(FIRST_NAMES, LAST_NAMES)
            username = f"{fn.lower()}.{ln.lower().replace(' ', '')}_{random.randint(10, 99)}"
            email = f"{username}@student.dlsu.edu.ph"
            student, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "first_name": fn,
                    "last_name": ln,
                },
            )
            profile, _ = Profile.objects.get_or_create(user=student)
            if profile.role != Profile.Role.STUDENT or profile.school != school:
                profile.role = Profile.Role.STUDENT
                profile.school = school
                profile.save()
            Enrollment.objects.get_or_create(student=student, course=course)
            SectionEnrollment.objects.get_or_create(student=student, section=section)
            section_students.append(student)

        all_students_by_section[section.id] = section_students
        print(f"  → {len(section_students)} students enrolled in {sec_name}")

    # ── Activities + Questions ──
    assignments_created = []

    for act_def in ALL_ACTIVITIES:
        assignment = Assignment.objects.create(
            course=course,
            course_section=None,  # shared across all sections
            activity_section=quizzes_section,
            activity_type=Assignment.ActivityType.QUIZ,
            title=act_def["title"],
            instructions=act_def["instructions"],
            max_score=Decimal("0.00"),
            instructor=instructor,
            time_limit_minutes=45,
            due_at=timezone.now() + timezone.timedelta(days=random.randint(7, 21)),
        )

        q_objects = []
        for idx, q_def in enumerate(act_def["questions"], start=1):
            kwargs = {
                "assignment": assignment,
                "text": q_def["text"],
                "question_type": q_def["type"],
                "points": Decimal(q_def["points"]),
                "order": idx,
            }
            if q_def["type"] == "multiple_choice":
                kwargs["choices"] = q_def["choices"]
                kwargs["correct_answers"] = q_def["correct_answers"]
            elif q_def["type"] == "true_false":
                kwargs["correct_answer"] = q_def["correct_answer"]
            elif q_def["type"] == "number":
                kwargs["correct_answer"] = q_def["correct_answer"]
                kwargs["answer_settings"] = q_def.get("answer_settings", {})

            q_objects.append(Question.objects.create(**kwargs))

        assignment.max_score = sum(q.points for q in q_objects)
        assignment.save()
        assignments_created.append((assignment, act_def["questions"], q_objects))
        print(f"Created Activity: {assignment.title}  ({len(q_objects)} questions, {assignment.max_score} pts)")

    # ── Submissions for every student in every section ──
    total_subs = 0
    for section in all_sections:
        students = all_students_by_section[section.id]
        for assignment, q_defs, q_objs in assignments_created:
            for student in students:
                answers = {}
                earned = Decimal("0.00")

                for q_def, q_obj in zip(q_defs, q_objs):
                    ans = GENERATORS[q_def["type"]](q_def)
                    answers[str(q_obj.id)] = ans
                    earned += score_answer(q_def, q_obj, ans)

                content = json.dumps({
                    "answers": answers,
                    "student_notes": f"Submitted by {student.get_full_name()}.",
                })

                is_graded = random.random() < 0.6  # 60% graded
                defaults = {"content": content, "attachment_url": ""}
                if is_graded:
                    defaults["score"] = earned
                    defaults["graded_at"] = timezone.now()
                    defaults["feedback"] = "Auto-graded by test script."
                else:
                    defaults["score"] = None
                    defaults["graded_at"] = None
                    defaults["feedback"] = ""

                Submission.objects.update_or_create(
                    assignment=assignment,
                    student=student,
                    defaults=defaults,
                )
                total_subs += 1

        print(f"  → Submissions created for {section.name}: {len(students)} students × {len(assignments_created)} activities")

    print(f"\n{'='*60}")
    print(f"  College Algebra course fully populated!")
    print(f"  School     : {school.name}")
    print(f"  Instructor : {instructor.get_full_name()}")
    print(f"  Sections   : {len(all_sections)}")
    print(f"  Students   : {sum(len(v) for v in all_students_by_section.values())} total")
    print(f"  Activities : {len(assignments_created)}")
    print(f"  Questions  : {sum(len(qo) for _, _, qo in assignments_created)} total")
    print(f"  Submissions: {total_subs} total")
    print(f"{'='*60}")


if __name__ == "__main__":
    run()
