#!/bin/sh

for argument in "$@"; do
  if [ "$argument" = "https://astral.sh/uv/0.9.5/install.sh" ]; then
    # uv and uvx were copied into PATH after the agent phase. The benchmark's
    # installer pipe may therefore complete without contacting astral.sh.
    exit 0
  fi
done

for candidate in /usr/bin/curl /usr/local/bin/curl /bin/curl; do
  if [ -x "$candidate" ]; then
    exec "$candidate" "$@"
  fi
done

echo "cached curl wrapper could not find the system curl" >&2
exit 127
