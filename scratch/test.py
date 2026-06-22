import re
import subprocess

with open('academics/templates/academics/assignment_form.html', 'r', encoding='utf-8') as f:
    content = f.read()

scripts = re.findall(r'<script>(.*?)</script>', content, re.DOTALL)
for i, script in enumerate(scripts):
    with open(f'scratch/script_{i}.js', 'w', encoding='utf-8') as f:
        f.write(script)
    try:
        res = subprocess.run(['node', '-c', f'scratch/script_{i}.js'], capture_output=True, text=True)
        print(f"Script {i} syntax check:", res.returncode)
        if res.returncode != 0:
            print(res.stderr)
    except Exception as e:
        print(e)
