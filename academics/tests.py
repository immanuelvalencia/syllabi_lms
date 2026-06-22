from decimal import Decimal

from django.test import SimpleTestCase

from .activity_questions import normalize_questions_payload, sanitize_question_html


class ActivityQuestionNormalizationTests(SimpleTestCase):
    def test_multiple_choice_keeps_structured_choices_and_multiple_correct_answers(self):
        questions = normalize_questions_payload([
            {
                "text": "<p>Select the prime numbers.</p>",
                "type": "multiple_choice",
                "points": "2.5",
                "choices": [
                    {"id": "a", "label": "A", "text": "2"},
                    {"id": "b", "label": "B", "text": "3"},
                    {"id": "c", "label": "C", "text": "4"},
                    {"id": "d", "label": "D", "text": "6"},
                ],
                "correct_answers": ["a", "b"],
            }
        ])

        question = questions[0]
        self.assertEqual(question["points"], Decimal("2.5"))
        self.assertEqual(len(question["choices"]), 4)
        self.assertEqual(question["choices"][0]["label"], "A")
        self.assertEqual(question["correct_answers"], ["a", "b"])
        self.assertEqual(question["correct_answer"], "a, b")

    def test_number_tolerance_is_stored_as_percent_with_computed_range(self):
        questions = normalize_questions_payload([
            {
                "text": "Measure the pH.",
                "type": "number",
                "points": "1.25",
                "correct_answers": ["80"],
                "tolerance_percent": "12.5",
            }
        ])

        question = questions[0]
        self.assertEqual(question["points"], Decimal("1.25"))
        self.assertEqual(question["answer_settings"]["tolerance_percent"], "12.5")
        self.assertEqual(question["answer_settings"]["accepted_range"], {"min": "70", "max": "90"})

    def test_rich_text_sanitizer_keeps_images_and_latex_but_removes_scripts(self):
        html = (
            '<p>Find <script>alert("x")</script></p>'
            '<img src="data:image/png;base64,abc" style="width: 75%;">'
            '<span class="math-expression" data-latex="\\frac{x}{2}" data-display="inline">\\(\\frac{x}{2}\\)</span>'
        )

        sanitized = sanitize_question_html(html)

        self.assertIn("data:image/png;base64,abc", sanitized)
        self.assertIn("width: 75%", sanitized)
        self.assertIn('data-latex="\\frac{x}{2}"', sanitized)
        self.assertNotIn("<script", sanitized)


from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import School, Profile, Course, CourseSection, ActivitySection, Assignment, Question, Submission
import json

User = get_user_model()

class AssignmentSubmissionTests(TestCase):
    def setUp(self):
        # Create users
        self.teacher = User.objects.create_user(username="teacher", password="password", email="teacher@example.com")
        self.student = User.objects.create_user(username="student", password="password", email="student@example.com")
        
        # Update profiles (already created by signal)
        teacher_profile, _ = Profile.objects.get_or_create(user=self.teacher)
        teacher_profile.role = Profile.Role.ACADEMIC_ADMIN
        teacher_profile.save()

        student_profile, _ = Profile.objects.get_or_create(user=self.student)
        student_profile.role = Profile.Role.STUDENT
        student_profile.save()
        
        # Create course
        self.course = Course.objects.create(
            title="Introduction to Programming",
            code="CS101",
            slug="cs101",
            instructor=self.teacher,
        )
        
        # Setup ActivitySection
        self.activity_section = ActivitySection.objects.create(
            course=self.course,
            name="Quizzes",
            order=1
        )
        
        # Setup Assignment
        self.assignment = Assignment.objects.create(
            course=self.course,
            activity_section=self.activity_section,
            activity_type=Assignment.ActivityType.QUIZ,
            title="Quiz 1",
            max_score=Decimal("10.00"),
            instructor=self.teacher,
        )
        
        # MCQ Question (Points: 3)
        self.q_mcq = Question.objects.create(
            assignment=self.assignment,
            text="What is 1 + 1?",
            question_type=Question.QuestionType.MULTIPLE_CHOICE,
            points=Decimal("3.00"),
            choices=[
                {"id": "a", "label": "A", "text": "1"},
                {"id": "b", "label": "B", "text": "2"},
                {"id": "c", "label": "C", "text": "3"},
            ],
            correct_answers=["b"],
            order=1
        )
        
        # TF Question (Points: 2)
        self.q_tf = Question.objects.create(
            assignment=self.assignment,
            text="Python is compiled.",
            question_type=Question.QuestionType.TRUE_FALSE,
            points=Decimal("2.00"),
            correct_answer="False",
            order=2
        )
        
        # Number Question with range (Points: 3)
        self.q_num = Question.objects.create(
            assignment=self.assignment,
            text="Enter a value close to 3.14.",
            question_type=Question.QuestionType.NUMBER,
            points=Decimal("3.00"),
            correct_answer="3.14",
            answer_settings={"accepted_range": {"min": "3.10", "max": "3.20"}},
            order=3
        )
        
        # Text Question (Points: 2) - needs manual grading
        self.q_text = Question.objects.create(
            assignment=self.assignment,
            text="Explain why you love coding.",
            question_type=Question.QuestionType.TEXT,
            points=Decimal("2.00"),
            order=4
        )

    def test_student_quiz_submission_and_auto_grading(self):
        # Enroll student in the course
        from .models import Enrollment
        Enrollment.objects.create(student=self.student, course=self.course)
        
        self.client.login(username="student", password="password")
        url = self.assignment.get_absolute_url()
        
        # Submit answers
        post_data = {
            f"question_{self.q_mcq.id}": "b",        # Correct MCQ
            f"question_{self.q_tf.id}": "False",     # Correct TF
            f"question_{self.q_num.id}": "3.15",     # Correct Number (in range)
            f"question_{self.q_text.id}": "I like python.",  # Text field (open ended, triggers manual grade flag)
            "content": "Done with the quiz!",
            "attachment_url": "https://example.com/work"
        }
        
        response = self.client.post(url, post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        # Since there is a text question, the assignment cannot be fully auto-graded.
        # Let's verify submission creation and status
        sub = Submission.objects.get(assignment=self.assignment, student=self.student)
        self.assertIsNone(sub.score) # Awaiting manual grading for text question
        
        # Parse saved answers from content
        data = json.loads(sub.content)
        self.assertEqual(data["answers"][str(self.q_mcq.id)], "b")
        self.assertEqual(data["answers"][str(self.q_tf.id)], "False")
        self.assertEqual(data["answers"][str(self.q_num.id)], "3.15")
        self.assertEqual(data["answers"][str(self.q_text.id)], "I like python.")
        self.assertEqual(data["student_notes"], "Done with the quiz!")
        self.assertEqual(sub.attachment_url, "https://example.com/work")
        
    def test_student_auto_graded_quiz(self):
        # Delete text question to make it fully auto-gradeable
        self.q_text.delete()
        
        from .models import Enrollment
        Enrollment.objects.create(student=self.student, course=self.course)
        
        self.client.login(username="student", password="password")
        url = self.assignment.get_absolute_url()
        
        post_data = {
            f"question_{self.q_mcq.id}": "b",        # Correct MCQ (+3)
            f"question_{self.q_tf.id}": "True",      # Incorrect TF (Correct is False) (0)
            f"question_{self.q_num.id}": "3.12",     # Correct Number (in range) (+3)
            "content": "Fully auto-graded quiz",
        }
        
        response = self.client.post(url, post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        # Submission should be auto-graded immediately
        sub = Submission.objects.get(assignment=self.assignment, student=self.student)
        self.assertEqual(sub.score, Decimal("6.00")) # 3 MCQ + 3 Number = 6
        self.assertIsNotNone(sub.graded_at)
        self.assertEqual(sub.feedback, "Auto-graded by System.")

    def test_teacher_grade_submission_view_get(self):
        # Create student submission
        sub = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            content=json.dumps({
                "answers": {
                    str(self.q_mcq.id): "b",
                    str(self.q_tf.id): "False",
                    str(self.q_num.id): "3.15",
                    str(self.q_text.id): "I like python."
                },
                "student_notes": "Done!"
            }),
            attachment_url="https://example.com/work"
        )
        
        # Instructor login
        self.client.login(username="teacher", password="password")
        from django.urls import reverse
        url = reverse("academics:grade_submission", kwargs={
            "slug": self.course.public_id,
            "assignment_id": self.assignment.public_id,
            "student_id": self.student.id
        })
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Explain why you love coding.")
        self.assertContains(response, "I like python.")
        self.assertContains(response, "https://example.com/work")

    def test_teacher_grade_submission_view_post_grade(self):
        # Create student submission
        sub = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            content=json.dumps({
                "answers": {
                    str(self.q_mcq.id): "b"
                },
                "student_notes": "Done!"
            })
        )
        
        # Instructor login
        self.client.login(username="teacher", password="password")
        from django.urls import reverse
        url = reverse("academics:grade_submission", kwargs={
            "slug": self.course.public_id,
            "assignment_id": self.assignment.public_id,
            "student_id": self.student.id
        })
        
        grade_data = {
            "action": "grade_submission",
            "score": "9.50",
            "feedback": "Outstanding work!"
        }
        
        response = self.client.post(url, grade_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify submission has been updated
        sub.refresh_from_db()
        self.assertEqual(sub.score, Decimal("9.50"))
        self.assertEqual(sub.feedback, "Outstanding work!")
        self.assertIsNotNone(sub.graded_at)

    from unittest.mock import patch
    @patch("academics.tasks.generate_submission_analysis_task")
    def test_teacher_grade_submission_view_post_ai_analysis(self, mock_task):
        # Create student submission
        sub = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            content=json.dumps({
                "answers": {
                    str(self.q_mcq.id): "b"
                },
                "student_notes": "Done!"
            })
        )
        
        # Instructor login
        self.client.login(username="teacher", password="password")
        from django.urls import reverse
        url = reverse("academics:grade_submission", kwargs={
            "slug": self.course.public_id,
            "assignment_id": self.assignment.public_id,
            "student_id": self.student.id
        })
        
        analysis_data = {
            "action": "analyze_submission"
        }
        
        response = self.client.post(url, analysis_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify status is saved as PENDING
        sub.refresh_from_db()
        self.assertEqual(sub.ai_analysis, "PENDING")
        mock_task.delay.assert_called_once()

    @patch("academics.services.generate_submission_analysis")
    def test_generate_submission_analysis_task_execution(self, mock_generate):
        mock_generate.return_value = "Detailed Feedback Report"
        
        sub = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            content=json.dumps({
                "answers": {
                    str(self.q_mcq.id): "b"
                },
                "student_notes": "Done!"
            })
        )
        
        from academics.tasks import generate_submission_analysis_task
        generate_submission_analysis_task(sub.id, [], "Done!")
        
        sub.refresh_from_db()
        self.assertEqual(sub.ai_analysis, "Detailed Feedback Report")
        mock_generate.assert_called_once()

    def test_student_access_grade_submission_forbidden(self):
        # Student login
        self.client.login(username="student", password="password")
        from django.urls import reverse
        url = reverse("academics:grade_submission", kwargs={
            "slug": self.course.public_id,
            "assignment_id": self.assignment.public_id,
            "student_id": self.student.id
        })
        
        response = self.client.get(url)
        # Should raise PermissionDenied resulting in 403 status code
        self.assertEqual(response.status_code, 403)
        
        response = self.client.post(url, {"action": "grade_submission", "score": "5.00"})
        self.assertEqual(response.status_code, 403)
