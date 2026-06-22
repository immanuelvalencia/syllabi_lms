from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from academics.activity_questions import sanitize_question_html


register = template.Library()


@register.filter
def question_content(question):
    content = question.content or {}
    html = content.get("html") or question.text
    if content.get("html"):
        return mark_safe(sanitize_question_html(html))
    return conditional_escape(question.text)


@register.filter
def choice_is_correct(question, choice):
    if not isinstance(choice, dict):
        return str(choice) == question.correct_answer or str(choice) in [str(answer) for answer in (question.correct_answers or [])]
    return str(choice.get("id", "")) in [str(answer) for answer in (question.correct_answers or [])]


@register.filter
def choice_label(choice, index=0):
    if isinstance(choice, dict):
        return choice.get("label") or chr(65 + int(index))
    return chr(65 + int(index))


@register.filter
def choice_text(choice):
    if isinstance(choice, dict):
        return choice.get("text", "")
    return str(choice)


@register.filter
def answer_label(question):
    if question.question_type == "multiple_choice":
        labels = [
            choice.get("label", "")
            for choice in question.choices
            if isinstance(choice, dict)
            if str(choice.get("id", "")) in [str(answer) for answer in (question.correct_answers or [])]
        ]
        return ", ".join(labels) or question.correct_answer
    if question.correct_answers:
        return ", ".join(str(answer) for answer in question.correct_answers)
    return question.correct_answer
