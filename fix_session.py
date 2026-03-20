import os

filepath = 'app.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('session.get("user", "admin")', 'session.get("username", "admin")')
content = content.replace('session.get("user")', 'session.get("username")')

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated app.py successfully.")
