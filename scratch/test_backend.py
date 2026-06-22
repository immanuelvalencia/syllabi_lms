import sys
import os
import django

sys.path.append('c:\\Users\\Jim\\Development\\syllabi_lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from academics.activity_questions import normalize_question_payload

payload = {
    "type": "text",
    "text": '<span class="image-resize-wrapper" style="width: 300px;"><img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="></span>',
    "points": 1
}

res = normalize_question_payload(payload)
print(res)
