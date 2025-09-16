# Udaan – Accessible AI-Powered Learning Platform

Udaan is a Flask-based web app that helps students with diverse learning needs. It supports AI summaries, translations (with Indic font embedding), dyslexia-friendly reading, audio narration, flashcards, quizzes, a student dashboard, and a teacher dashboard with class insights.

## Features
- Student auth and dashboard
  - Upload textbooks (PDF/DOCX/TXT → text extraction + OCR fallback)
  - Audio narration (TTS), AI summaries (Gemini), translations (Hindi PDF with Noto fonts)
  - Dyslexic-friendly reader with adjustable spacing, overlays, and in-page TTS
  - Flashcards and MCQ quizzes via Gemini
  - Library of uploaded books
- Teacher auth and dashboard
  - Upload/view books, dynamic class stats, recent students (activity-ranked)
  - Student progress view (uploads, flashcards, quizzes, avg score)
- SQLite storage for users, uploads, flashcards, quiz attempts

## Tech Stack
- Backend: Python, Flask, SQLite
- AI: Google Generative AI (Gemini)
- PDF/Image: PyPDF2, pdf2image, PyMuPDF (fitz), Pillow
- OCR: Tesseract (pytesseract)
- PDF generation: reportlab
- Frontend: Jinja templates, vanilla JS, modern responsive CSS

## Repository Structure
```
app/                    # Global styles (Next.js-like folder kept for future)
project/
  app.py                # Flask app entrypoint
  requirements.txt      # Python dependencies
  database.db           # SQLite DB (auto-created)
  static/
    books/              # Teacher-uploaded books
    translations/       # Generated translated PDFs
    narrations/         # Generated audio files
    audio/              # Sample audio
    styles.css          # Shared CSS
    bot.jpg             # Friendly robot image
  templates/            # Jinja2 templates (auth, dashboards, readers, etc.)
  uploads/              # Student uploads
  Noto_Sans_Devanagari/ # Fonts for Hindi PDF output
```

## Prerequisites
- Python 3.10+
- Windows (paths below assume Windows; adjust for macOS/Linux accordingly)
- Tesseract OCR installed (Windows path example):
  - Install: https://github.com/tesseract-ocr/tesseract
  - Ensure the path matches the one configured in `project/app.py`:
    - `pytesseract.pytesseract.tesseract_cmd = "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"`
- (Recommended) Poppler for `pdf2image` (Windows build: https://github.com/oschwartz10612/poppler-windows)
- Google Generative AI key (Gemini)

## Setup
1) Create and activate a virtual environment
```
cd project
python -m venv venv
venv\Scripts\activate
```

2) Install dependencies
```
pip install -r requirements.txt
```

3) Configure environment variables
- Create a `.env` file in `project/`:
```
GEMINI_API_KEY=your_gemini_api_key_here
```

4) Verify asset paths
- Tesseract path in `app.py` (edit if your install path differs)
- Optional: Ensure Poppler is installed and on PATH if `pdf2image` needs it

5) Run the app
```
python app.py
```
- App runs at `http://127.0.0.1:5000/`

## Usage Overview
- Landing page → Role selection (Student / Teacher)
- Student
  - Sign up / login → Student dashboard
  - Upload a textbook (PDF preferred); OCR fallback used for scans/images
  - Use features: Audio, Summary, Translation (Hindi PDF), Dyslexic Reader, Flashcards, Quizzes
  - Library lists teacher-uploaded PDFs from `static/books`
- Teacher
  - Sign up / login → Teacher dashboard (live stats from DB)
  - Upload/view books (static library)
  - View student progress with uploads/flashcards/quizzes and averages

## Important Paths & Fonts
- Hindi PDF output uses Noto Sans Devanagari
  - Files included in `project/Noto_Sans_Devanagari/`
  - Ensure the app reads `NotoSansDevanagari-Regular.ttf` in `project/`
- Translations are written to `project/static/translations/`
- Narrations are written to `project/static/narrations/`

## Security Notes
- Default `app.secret_key` in `app.py` is a dev placeholder. Set a strong secret in production.
- Avoid committing `.env` with real keys.
- Validate and sanitize file uploads in production; consider limiting file size and validating content-type.

## Troubleshooting
- Tesseract not found
  - Update `pytesseract.pytesseract.tesseract_cmd` in `app.py` to your install path
  - Confirm `tesseract.exe` runs from a terminal
- `pdf2image` errors on Windows
  - Install Poppler and add its `bin` directory to PATH
- Gemini errors
  - Verify `GEMINI_API_KEY` in `.env`
  - Check network/proxy issues
- Missing fonts for Hindi PDF
  - Ensure `NotoSansDevanagari-Regular.ttf` exists in `project/`

## Extending
- Replace placeholder charts with a JS chart library (e.g., Chart.js)
- Add per-student pages and deeper analytics
- Persist dyslexic reader preferences (localStorage)
- Add server-side MP3 generation endpoint (pyttsx3 already integrated client-side; extend as needed)

## License
- Fonts licensed per included OFL.
- App code: MIT (customize as needed).
