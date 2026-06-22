from decimal import Decimal, InvalidOperation
import re

from bs4 import BeautifulSoup


ALLOWED_CONTENT_TAGS = {
    "b",
    "br",
    "div",
    "em",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "span",
    "strong",
    "sub",
    "sup",
    "u",
    "ul",
}
MATH_CLASSES = {"math-expression", "math-block"}


def decimal_from_value(value, default="0"):
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)
    return decimal_value if decimal_value >= 0 else Decimal(default)


def decimal_to_string(value):
    value = decimal_from_value(value)
    return format(value.normalize(), "f") if value else "0"


def _clean_style(style):
    width_match = re.search(r"(?:^|;)\s*width\s*:\s*([0-9]{1,4})(?:\.[0-9]+)?(%|px)\s*(?:;|$)", style or "", re.I)
    if not width_match:
        return ""
    val = int(width_match.group(1))
    unit = width_match.group(2)
    if unit == "%":
        width = min(100, max(10, val))
        return f"width: {width}%; max-width: 100%; height: auto;"
    else:
        width = min(2000, max(20, val))
        return f"width: {width}px; max-width: 100%; height: auto;"


def sanitize_question_html(html):
    soup = BeautifulSoup(html or "", "html.parser")

    for tag in list(soup.find_all(True)):
        if tag.name not in ALLOWED_CONTENT_TAGS:
            tag.unwrap()
            continue

        attrs = {}
        if tag.name == "img":
            src = tag.get("src", "")
            if not re.match(r"^data:image/(png|jpe?g|gif|webp);base64,", src, re.I) and not src.startswith(("/media/", "http://", "https://")):
                tag.decompose()
                continue
            attrs["src"] = src
            attrs["alt"] = tag.get("alt", "")
            attrs["style"] = _clean_style(tag.get("style", "")) or "width: 60%; max-width: 100%; height: auto;"
            image_id = tag.get("data-image-id", "")
            if re.match(r"^[a-zA-Z0-9_-]{1,80}$", image_id):
                attrs["data-image-id"] = image_id
            attrs["class"] = tag.get("class", ["question-image"])
        elif tag.name in {"span", "div"}:
            classes = set(tag.get("class", []))
            if classes & MATH_CLASSES:
                class_name = "math-block" if "math-block" in classes else "math-expression"
                attrs["class"] = class_name
                attrs["data-display"] = "block" if tag.get("data-display") == "block" else "inline"
                attrs["data-latex"] = str(tag.get("data-latex", ""))[:5000]
            elif "image-resize-wrapper" in classes:
                attrs["class"] = " ".join(classes)
                attrs["style"] = _clean_style(tag.get("style", ""))
                attrs["contenteditable"] = "false"
        elif tag.name in {"ol", "ul"}:
            attrs["class"] = "list-decimal pl-5" if tag.name == "ol" else "list-disc pl-5"

        tag.attrs = attrs

    return soup.decode_contents().strip()


def plain_text_from_html(html):
    soup = BeautifulSoup(html or "", "html.parser")
    return soup.get_text(" ", strip=True)


def accepted_numeric_range(answer, tolerance_percent):
    answer_decimal = decimal_from_value(answer)
    tolerance_decimal = decimal_from_value(tolerance_percent)
    offset = abs(answer_decimal) * tolerance_decimal / Decimal("100")
    minimum = answer_decimal - offset
    maximum = answer_decimal + offset
    return {
        "min": format(minimum.normalize(), "f"),
        "max": format(maximum.normalize(), "f"),
    }


def _choice_id(index, choice):
    existing_id = choice.get("id") if isinstance(choice, dict) else ""
    if existing_id and re.match(r"^[a-zA-Z0-9_-]{1,80}$", str(existing_id)):
        return str(existing_id)
    return f"choice_{index + 1}"


def normalize_choice_items(choices):
    normalized = []
    for index, choice in enumerate(choices or []):
        if isinstance(choice, dict):
            text = str(choice.get("text", "")).strip()
            label = str(choice.get("label", "")).strip() or chr(65 + index)
        else:
            text = str(choice).strip()
            label = chr(65 + index)
        normalized.append({
            "id": _choice_id(index, choice if isinstance(choice, dict) else {}),
            "label": label[:3],
            "text": text,
        })
    return normalized


def normalize_question_payload(question_data):
    question_type = question_data.get("type") or question_data.get("question_type") or "text"
    if question_type not in {"multiple_choice", "true_false", "text", "number"}:
        question_type = "text"

    content = question_data.get("content") if isinstance(question_data.get("content"), dict) else {}
    html = sanitize_question_html(content.get("html") or question_data.get("text_html") or question_data.get("text") or "")
    plain_text = plain_text_from_html(html)
    points = decimal_from_value(question_data.get("points", 1), default="1")
    correct_answers = question_data.get("correct_answers", [])
    if not isinstance(correct_answers, list):
        correct_answers = [correct_answers]
    answer_settings = {}

    choices = []
    legacy_correct_answer = str(question_data.get("correct_answer", "")).strip()
    if question_type == "multiple_choice":
        choices = normalize_choice_items(question_data.get("choices") or [])
        if not choices:
            choices = normalize_choice_items([
                {"text": "Choice A"},
                {"text": "Choice B"},
                {"text": "Choice C"},
                {"text": "Choice D"},
            ])
        choice_ids = {choice["id"] for choice in choices}
        legacy_matches = [
            choice["id"]
            for choice in choices
            if legacy_correct_answer and legacy_correct_answer in {choice["id"], choice["text"], choice["label"]}
        ]
        correct_answers = [str(answer) for answer in correct_answers if str(answer) in choice_ids] or legacy_matches
    elif question_type == "true_false":
        answer = str((correct_answers[0] if correct_answers else legacy_correct_answer) or "True")
        correct_answers = ["False" if answer.lower() == "false" else "True"]
    elif question_type == "number":
        answer = str(correct_answers[0] if correct_answers else legacy_correct_answer).strip()
        tolerance_percent = question_data.get("tolerance_percent")
        if tolerance_percent is None and isinstance(question_data.get("answer_settings"), dict):
            tolerance_percent = question_data["answer_settings"].get("tolerance_percent", 0)
        tolerance_percent = decimal_from_value(tolerance_percent)
        correct_answers = [answer] if answer else []
        answer_settings = {
            "tolerance_percent": decimal_to_string(tolerance_percent),
            "accepted_range": accepted_numeric_range(answer or "0", tolerance_percent),
        }
    else:
        answer = str(correct_answers[0] if correct_answers else legacy_correct_answer).strip()
        correct_answers = [answer] if answer else []

    correct_answer_text = ", ".join(correct_answers)
    return {
        "text": html or plain_text,
        "content": {
            "html": html,
            "plain_text": plain_text,
        },
        "type": question_type,
        "points": points,
        "choices": choices,
        "correct_answers": correct_answers,
        "correct_answer": correct_answer_text,
        "answer_settings": answer_settings,
    }


def normalize_questions_payload(questions_data):
    if not isinstance(questions_data, list):
        return []
    return [normalize_question_payload(question) for question in questions_data if isinstance(question, dict)]


def question_to_editor_payload(question):
    correct_answers = list(question.correct_answers or [])
    if not correct_answers and question.correct_answer:
        correct_answers = [question.correct_answer]
    return {
        "text": question.text,
        "content": question.content or {"html": question.text, "plain_text": plain_text_from_html(question.text)},
        "type": question.question_type,
        "points": decimal_to_string(question.points),
        "choices": normalize_choice_items(question.choices),
        "correct_answers": correct_answers,
        "correct_answer": question.correct_answer,
        "answer_settings": question.answer_settings or {},
        "tolerance_percent": (question.answer_settings or {}).get("tolerance_percent", "0"),
    }
