#!/bin/bash
# Double-click this file to start the Cath Hemo app.
cd "$(dirname "$0")"

echo "Starting Cath Hemo..."

# Start the API server in the background
python3 -m uvicorn api.main:app --port 8000 &
API_PID=$!

# Give it a moment then open the editor
sleep 2
open "http://localhost:8000/editor"

# Start Streamlit (opens automatically in browser)
python3 -m streamlit run app.py

# When Streamlit exits, also stop the API server
kill $API_PID 2>/dev/null
