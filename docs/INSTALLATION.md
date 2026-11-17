# Installation

Backend:
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

Frontend:
cd frontend
npm install
npm run dev

Health: GET http://127.0.0.1:8000/api/health
CORS: backend allows localhost:5173 and 127.0.0.1:5173.
```