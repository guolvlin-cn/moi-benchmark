import os
import sys

names = [
    "TOOLATHLON_DEEPSEEK_ASTRA_API_KEY",
    "TOOLATHLON_DEEPSEEK_HERMES_API_KEY",
    "ASTRA_ADMIN_ACCESS_TOKEN",
]

missing = []
for name in names:
    if os.environ.get(name):
        print(f"OK      {name}")
    else:
        print(f"MISSING {name}")
        missing.append(name)

a = os.environ.get("TOOLATHLON_DEEPSEEK_ASTRA_API_KEY")
h = os.environ.get("TOOLATHLON_DEEPSEEK_HERMES_API_KEY")

if a and h:
    if a == h:
        print("ERROR   Astra 与 Hermes 的 DeepSeek Key 相同")
        sys.exit(1)
    print("OK      Astra 与 Hermes 的 DeepSeek Key 不同")

if missing:
    sys.exit(1)
