#!/bin/sh
# Starts the local ear (web) server and opens it in the browser.
# Close this window (or Ctrl+C) to stop the server (not needed once the app is installed).
cd "$(dirname "$0")" || exit 1
if ! command -v node >/dev/null 2>&1; then
    echo "Node.js is not installed: download it from https://nodejs.org/"
    exit 1
fi
(sleep 1; if command -v open >/dev/null 2>&1; then open http://localhost:8080/; else xdg-open http://localhost:8080/; fi) >/dev/null 2>&1 &
exec node server.js
