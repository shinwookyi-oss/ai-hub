import re
import subprocess
import tempfile
import sys

content = open("app.py", encoding="utf-8").read()
# Extract everything between <script> and </script>
scripts = re.findall(r'<script>(.*?)</script>', content, flags=re.DOTALL)
if not scripts:
    print("No scripts found")
    sys.exit()

js_code = scripts[0]
with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
    f.write(js_code)
    temp_path = f.name

try:
    result = subprocess.run(["node", "-c", temp_path], capture_output=True, text=True)
    if result.returncode != 0:
        print("Syntax Error Found in JS!")
        print(result.stderr)
    else:
        print("JS Syntax OK!")
except Exception as e:
    print(f"Could not run node: {e}")
finally:
    import os
    os.remove(temp_path)
