from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import PyPDF2
import pyttsx3
import time
import google.generativeai as genai
from deep_translator import GoogleTranslator
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from googletrans import Translator
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from PyPDF2 import PdfReader
import fitz 
import pytesseract
from PIL import Image
import json
import re
from pdf2image import convert_from_path
import pytesseract
import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load .env file
load_dotenv()

# Get the API key from .env
api_key = os.getenv("GEMINI_API_KEY")

# Configure Gemini (only once)
genai.configure(api_key=api_key)

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


app = Flask(__name__)
app.secret_key = "dev-secret-change-this"  
DB = "database.db"
books=[]

BOOKS_FOLDER = os.path.join("static", "books")
os.makedirs(BOOKS_FOLDER, exist_ok=True)

UPLOAD_FOLDER = "uploads"
AUDIO_FOLDER = "static/audio"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Hybrid PDF Text Extraction
def extract_text_hybrid(pdf_path):
    """Try PyPDF2 first, if no text then fallback to OCR."""
    text = ""
    try:
        pdf_reader = PyPDF2.PdfReader(open(pdf_path, "rb"))
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        print("⚠️ Error reading with PyPDF2:", e)

    if text.strip():
        return text

    # Fallback: OCR
    print("⚠️ No text found, using OCR...")
    try:
        pages = convert_from_path(pdf_path)
        for page in pages:
            text += pytesseract.image_to_string(page)
    except Exception as e:
        print("⚠️ OCR failed:", e)

    return text

def text_to_pdf(text, output_pdf, font_path, font_size=12):
    pdfmetrics.registerFont(TTFont("CustomFont", font_path))
    c = canvas.Canvas(output_pdf, pagesize=A4)
    width, height = A4
    textobject = c.beginText(50, height - 50)
    textobject.setFont("CustomFont", font_size)
    for line in text.split("\n"):
        textobject.textLine(line)
    c.drawText(textobject)
    c.showPage()
    c.save()

# Translation 
def translate_pdf_to_pdf(input_pdf, output_pdf, target_lang, font_path):
    font_name = f"Font_{target_lang}"
    pdfmetrics.registerFont(TTFont(font_name, font_path))
    translator = Translator()

    with open(input_pdf, "rb") as book:
        reader = PyPDF2.PdfReader(book)
        c = canvas.Canvas(output_pdf, pagesize=A4)
        width, height = A4

        for num in range(len(reader.pages)):
            text = reader.pages[num].extract_text()
            if text:
                translated = translator.translate(text, dest=target_lang).text
                textobject = c.beginText(50, height - 50)
                textobject.setFont(font_name, 12)

                for line in translated.split("\n"):
                    textobject.textLine(line)

                c.drawText(textobject)
                c.showPage()

        c.save()

# DB Setup 
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        age INTEGER,
        grade TEXT,
        accessibility TEXT,
        email TEXT,
        phone TEXT,
        password_hash TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        password_hash TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        filename TEXT,
        uploaded_at TEXT,
        FOREIGN KEY(student_id) REFERENCES students(id)
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS flashcards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        filename TEXT,
        num_flashcards INTEGER,
        created_at TEXT,
        FOREIGN KEY(student_id) REFERENCES students(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS quiz_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        quiz_id TEXT,
        score INTEGER,
        total INTEGER,
        attempted_at TEXT,
        FOREIGN KEY(student_id) REFERENCES students(id)
    )""")
    
    conn.commit()
    conn.close()


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user = session.get("user")
            if not user:
                flash("Please log in first.")
                return redirect(url_for("index"))
            if role and user.get("role") != role:
                flash(f"Access restricted to {role}s only.")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return wrapped
    return decorator

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/role/<role>")
def role_page(role):
    role = role.lower()
    if role not in ("student", "teacher"):
        flash("Invalid role selected.")
        return redirect(url_for("index"))
    return render_template("auth_options.html", role=role)

# Student signup/login 
@app.route("/signup/student", methods=["GET", "POST"])
def signup_student():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        age = request.form.get("age") or None
        grade = request.form.get("grade") or None
        accessibility = request.form.get("accessibility") or None
        email = request.form.get("email") or None
        phone = request.form.get("phone") or None
        password = request.form.get("password") or None

        if not name:
            flash("Name is required.")
            return redirect(request.url)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM students WHERE name = ?", (name,))
        if cur.fetchone():
            flash("A student with that name already exists.")
            conn.close()
            return redirect(url_for("role_page", role="student"))

        if not password:
            flash("Password is required.")
            conn.close()
            return redirect(request.url)

        password_hash = generate_password_hash(password)
        cur.execute("""
            INSERT INTO students (name, age, grade, accessibility, email, phone, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, age, grade, accessibility, email, phone, password_hash, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        flash("Student signed up successfully. Please login.")
        return redirect(url_for("role_page", role="student"))
    return render_template("signup_student.html")

@app.route("/login/student", methods=["GET", "POST"])
def login_student():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM students WHERE name = ?", (name,))
        user = cur.fetchone()
        conn.close()

        if not user:
            flash("Student not found. Please sign up.")
            return redirect(request.url)

        if user["password_hash"] and check_password_hash(user["password_hash"], password):
            session["user"] = {"role": "student", "id": user["id"], "name": user["name"]}
            return redirect(url_for("student_dashboard"))
        else:
            flash("Incorrect password.")
            return redirect(request.url)
    return render_template("login_student.html")

# Teacher signup/login
@app.route("/signup/teacher", methods=["GET", "POST"])
def signup_teacher():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email") or None
        phone = request.form.get("phone") or None
        password = request.form.get("password") or None
        if not name:
            flash("Name is required.")
            return redirect(request.url)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM teachers WHERE name = ?", (name,))
        if cur.fetchone():
            flash("A teacher/parent with that name already exists.")
            conn.close()
            return redirect(url_for("role_page", role="teacher"))

        if not password:
            flash("Password is required.")
            conn.close()
            return redirect(request.url)

        password_hash = generate_password_hash(password)
        cur.execute("""
            INSERT INTO teachers (name, email, phone, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, email, phone, password_hash, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        flash("Teacher/Parent signed up successfully. Please login.")
        return redirect(url_for("role_page", role="teacher"))
    return render_template("signup_teacher.html")

@app.route("/login/teacher", methods=["GET", "POST"])
def login_teacher():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM teachers WHERE name = ?", (name,))
        user = cur.fetchone()
        conn.close()

        if not user:
            flash("Teacher/Parent not found. Please sign up.")
            return redirect(request.url)

        if user["password_hash"] and check_password_hash(user["password_hash"], password):
            session["user"] = {"role": "teacher", "id": user["id"], "name": user["name"]}
            return redirect(url_for("teacher_dashboard"))
        else:
            flash("Incorrect password.")
            return redirect(request.url)
    return render_template("login_teacher.html")

# Student Dashboard 
@app.route("/dashboard/student")
@login_required(role="student")
def student_dashboard():
    user = session.get("user")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM uploads WHERE student_id = ?", (user["id"],))
    uploads = cur.fetchall()
    conn.close()
    return render_template("student_dashboard.html", name=user.get("name"), uploads=uploads)

@app.route("/upload_textbook", methods=["POST"])
@login_required(role="student")
def upload_textbook():
    if "textbook" not in request.files:
        flash("No file selected.")
        return redirect(url_for("student_dashboard"))
    file = request.files["textbook"]
    if file.filename == "":
        flash("No file selected.")
        return redirect(url_for("student_dashboard"))

    filename = file.filename
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    session["uploaded_file"] = filename
    user = session.get("user")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO uploads (student_id, filename, uploaded_at) VALUES (?, ?, ?)",
                (user["id"], filename, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    flash(f"Uploaded {filename} successfully ✅")
    return redirect(url_for("student_dashboard"))

@app.route("/library")
@login_required(role="student")
def library():
    books_folder = os.path.join(app.static_folder, "books")
    if not os.path.exists(books_folder):
        os.makedirs(books_folder)

    books = sorted(
        os.listdir(books_folder),
        key=lambda x: os.path.getmtime(os.path.join(books_folder, x)),
        reverse=True
    )

    return render_template("library.html", books=books)


@app.route("/audio_narration", methods=["POST"])
@login_required(role="student")
def audio_narration():
    filename = session.get("uploaded_file")
    if not filename:
        flash("No textbook uploaded yet.")
        return redirect(url_for("student_dashboard"))

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if not os.path.exists(filepath):
        flash("File not found on server.")
        return redirect(url_for("student_dashboard"))

    # extracting text directly 
    text = ""
    try:
        pdf_reader = PdfReader(open(filepath, "rb"))
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        flash(f"Error reading PDF: {str(e)}")
        return redirect(url_for("student_dashboard"))

    # Fallback to OCR 
    if not text.strip():
        flash("⚠️ No text found, using OCR...")
        try:
            doc = fitz.open(filepath)
            ocr_text = []
            for page_num in range(len(doc)):
                pix = doc[page_num].get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_text.append(pytesseract.image_to_string(img))
            text = "\n".join(ocr_text)
        except Exception as e:
            flash(f"⚠️ OCR failed: {str(e)}")
            return redirect(url_for("student_dashboard"))

    if not text.strip():
        flash("⚠️ Still no readable text found after OCR.")
        return redirect(url_for("student_dashboard"))

    # Generate narration
    student_id = session["user"]["id"]
    timestamp = int(time.time())
    audio_filename = f"{student_id}_{timestamp}.mp3"
    audio_path = os.path.join("static/narrations", audio_filename)
    os.makedirs("static/narrations", exist_ok=True)

    # Convert text to speech
    try:
        engine = pyttsx3.init()
        engine.save_to_file(text, audio_path)
        engine.runAndWait()
    except Exception as e:
        flash(f"Error generating narration: {str(e)}")
        return redirect(url_for("student_dashboard"))

    flash("🎧 Audio narration generated successfully!")

    user = session.get("user")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM uploads WHERE student_id = ?", (user["id"],))
    uploads = cur.fetchall()
    conn.close()

    return render_template(
        "student_dashboard.html",
        name=user.get("name"),
        uploads=uploads,
        audio_file=audio_filename
    )


@app.route("/generate_summary", methods=["POST"])
@login_required(role="student")
def generate_summary():
    filename = session.get("uploaded_file")
    if not filename:
        flash("No textbook uploaded yet.")
        return redirect(url_for("student_dashboard"))

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if not os.path.exists(filepath):
        flash("File not found on server.")
        return redirect(url_for("student_dashboard"))

    # extracting text directly 
    text = ""
    try:
        pdf_reader = PdfReader(open(filepath, "rb"))
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        flash(f"Error reading PDF: {str(e)}")
        return redirect(url_for("student_dashboard"))

    # Fallback to OCR 
    if not text.strip():
        flash("⚠️ No text found, using OCR...")
        try:
            doc = fitz.open(filepath)
            ocr_text = []
            for page_num in range(len(doc)):
                pix = doc[page_num].get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_text.append(pytesseract.image_to_string(img))
            text = "\n".join(ocr_text)
        except Exception as e:
            flash(f"⚠️ OCR failed: {str(e)}")
            return redirect(url_for("student_dashboard"))

    if not text.strip():
        flash("⚠️ Still no readable text found after OCR.")
        return redirect(url_for("student_dashboard"))

    # Generate summary via Gemini 
    flash("Generating summary... this may take a few seconds.")

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"Please provide a simplified summary without making the content bold or adding * of the following textbook content:\n\n{text[:10000]}"
        response = model.generate_content(prompt)
        summary = response.text
    except Exception as e:
        flash(f"Error generating summary: {str(e)}")
        return redirect(url_for("student_dashboard"))

    user = session.get("user")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM uploads WHERE student_id = ?", (user["id"],))
    uploads = cur.fetchall()
    conn.close()

    return render_template(
        "student_dashboard.html",
        name=user.get("name"),
        uploads=uploads,
        summary=summary,
        audio_file=session.get("audio_file")  
    )

@app.route("/translate_text", methods=["POST"])
@login_required(role="student")
def translate_text():
    filename = session.get("uploaded_file")
    if not filename:
        flash("No textbook uploaded yet.")
        return redirect(url_for("student_dashboard"))

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if not os.path.exists(filepath):
        flash("File not found on server.")
        return redirect(url_for("student_dashboard"))

    # --- Step 1: Extract text directly from PDF ---
    text = ""
    try:
        pdf_reader = PdfReader(open(filepath, "rb"))
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:  # only add if not None
                text += page_text
    except Exception as e:
        flash(f"Error reading PDF: {str(e)}")
        return redirect(url_for("student_dashboard"))

    # --- Step 2: Fallback to OCR if no text ---
    if not text.strip():
        flash("⚠️ No text found, using OCR...")
        try:
            doc = fitz.open(filepath)
            ocr_text = []
            for page_num in range(len(doc)):
                pix = doc[page_num].get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_result = pytesseract.image_to_string(img)
                ocr_text.append(ocr_result if isinstance(ocr_result, str) else "")
            text = "\n".join(ocr_text)
        except Exception as e:
            flash(f"⚠️ OCR failed: {str(e)}")
            return redirect(url_for("student_dashboard"))

    if not text.strip():
        flash("⚠️ Still no readable text found after OCR.")
        return redirect(url_for("student_dashboard"))

    # --- Step 3: Prepare output files ---
    os.makedirs("static/translations", exist_ok=True)
    base = os.path.splitext(filename)[0]
    hindi_file = f"{base}_hindi.pdf"
    kannada_file = f"{base}_kannada.pdf"
    hindi_path = os.path.join("static/translations", hindi_file)
    kannada_path = os.path.join("static/translations", kannada_file)

    # --- Step 4: Translation with Gemini ---
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")

        # Translate to Hindi
        prompt_hi = f"Translate the following English educational text into Hindi, keep it clear and natural and don't bold anything. No * please:\n\n{text}"
        response_hi = model.generate_content(prompt_hi)
        print("Gemini Hindi response:", response_hi.text)  # DEBUG
        hindi_text = response_hi.text if response_hi and response_hi.text else text

        # Translate to Kannada
        prompt_kn = f"Translate the following English educational text into Kannada, keep it clear and natural:\n\n{text}"
        response_kn = model.generate_content(prompt_kn)
        print("Gemini Kannada response:", response_kn.text)  # DEBUG
        kannada_text = response_kn.text if response_kn and response_kn.text else text

        # --- Step 5: Save PDFs with proper fonts ---
        text_to_pdf(
            hindi_text,
            hindi_path,
            font_path=r"NotoSansDevanagari-Regular.ttf"
        )
        text_to_pdf(
            kannada_text,
            kannada_path,
            font_path=r"C:\prewal\NotoSansKannada-Regular.ttf"
        )

    except Exception as e:
        flash(f"Error during translation: {str(e)}")
        return redirect(url_for("student_dashboard"))

    flash("✅ Translations ready for download!")

    # --- Step 6: Refresh uploads list for dashboard ---
    user = session.get("user")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM uploads WHERE student_id = ?", (user["id"],))
    uploads = cur.fetchall()
    conn.close()

    return render_template(
        "student_dashboard.html",
        name=user.get("name"),
        uploads=uploads,
        hindi_file=hindi_file,
        kannada_file=kannada_file
    )

@app.route("/dyslexic_friendly", methods=["POST"])
@login_required(role="student")
def dyslexic_friendly():
    filename = session.get("uploaded_file")
    if not filename:
        flash("No textbook uploaded yet.")
        return redirect(url_for("student_dashboard"))

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if not os.path.exists(filepath):
        flash("File not found on server.")
        return redirect(url_for("student_dashboard"))

    # extracting text directly
    text = ""
    try:
        pdf_reader = PdfReader(open(filepath, "rb"))
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        flash(f"Error reading PDF: {str(e)}")
        return redirect(url_for("student_dashboard"))

    # fallback to OCR
    if not text.strip():
        flash("⚠️ No text found, using OCR...")
        try:
            doc = fitz.open(filepath)
            ocr_text = []
            for page_num in range(len(doc)):
                pix = doc[page_num].get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_text.append(pytesseract.image_to_string(img))
            text = "\n".join(ocr_text)
        except Exception as e:
            flash(f"⚠️ OCR failed: {str(e)}")
            return redirect(url_for("student_dashboard"))

    if not text.strip():
        flash("⚠️ Still no readable text found after OCR.")
        return redirect(url_for("student_dashboard"))

    return render_template("dyslexic_reader.html", text=text)



@app.route("/generate_flashcards", methods=["POST"])
@login_required(role="student")
def generate_flashcards():
    filename = session.get("uploaded_file")
    if not filename:
        flash("No textbook uploaded yet.")
        return redirect(url_for("student_dashboard"))

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    # Try extracting text directly
    text = ""
    try:
        pdf_reader = PdfReader(open(filepath, "rb"))
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        flash(f"Error reading PDF: {str(e)}")
        return redirect(url_for("student_dashboard"))

    # Fallback to OCR ----------
    if not text.strip():
        flash("⚠️ No text found, using OCR...")
        try:
            doc = fitz.open(filepath)
            ocr_text = []
            for page_num in range(len(doc)):
                pix = doc[page_num].get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_text.append(pytesseract.image_to_string(img))
            text = "\n".join(ocr_text)
        except Exception as e:
            flash(f"⚠️ OCR failed: {str(e)}")
            return redirect(url_for("student_dashboard"))

    if not text.strip():
        flash("⚠️ Still no readable text found after OCR.")
        return redirect(url_for("student_dashboard"))

    # Gemini for flashcards 
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "Generate 10 flashcards from the following text. "
            "Return ONLY a JSON list in this format: "
            "[{\"question\": \"...\", \"answer\": \"...\"}].\n\n"
            f"Text:\n{text[:4000]}"
        )
        response = model.generate_content(prompt)

        raw = response.text.strip()

        # Clean Gemini’s output
        raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()

        # Extract only JSON list
        match = re.search(r"\[.*\]", raw, re.S)
        if not match:
            raise ValueError("Gemini did not return valid JSON")
        json_str = match.group()

        # Parse into Python list
        flashcards = json.loads(json_str)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""INSERT INTO flashcards (student_id, filename, num_flashcards, created_at)
    VALUES (?, ?, ?, ?)""", (session["user"]["id"], filename, len(flashcards), datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()


    except Exception as e:
        print("⚠️ Gemini raw output:", response.text if 'response' in locals() else "No response")
        flash(f"Error generating flashcards: {str(e)}")
        return redirect(url_for("student_dashboard"))

    return render_template("flashcard.html", flashcards=flashcards)

@app.route("/generate_quiz", methods=["POST"])
@login_required(role="student")
def generate_quiz():
    filename = session.get("uploaded_file")
    if not filename:
        flash("No textbook uploaded yet.")
        return redirect(url_for("student_dashboard"))

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    # Extract text
    text = ""
    try:
        pdf_reader = PdfReader(open(filepath, "rb"))
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        flash(f"Error reading PDF: {str(e)}")
        return redirect(url_for("student_dashboard"))

    # Fallback to OCR 
    if not text.strip():
        flash("⚠️ No text found, using OCR...")
        try:
            doc = fitz.open(filepath)
            ocr_text = []
            for page_num in range(len(doc)):
                pix = doc[page_num].get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_text.append(pytesseract.image_to_string(img))
            text = "\n".join(ocr_text)
        except Exception as e:
            flash(f"⚠️ OCR failed: {str(e)}")
            return redirect(url_for("student_dashboard"))

    if not text.strip():
        flash("⚠️ Still no readable text found after OCR.")
        return redirect(url_for("student_dashboard"))

    # Generate quiz with Gemini 
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"""
Create a multiple-choice quiz (MCQ) of 10 questionsfrom the following text.  
Make sure to cover all important concepts.  

⚠️ Important formatting rules:  
- Each option **must** start with a letter and a dot, like "A. ...", "B. ...", "C. ...", "D. ...".  
- The "answer" field must contain only the **letter** ("A", "B", "C", or "D"), not the full text.  

Strictly return valid JSON in this format:

[
  {{
    "question": "What is ...?",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "answer": "B"
  }},
  ...
]

Text:
{text[:6000]}
"""


        response = model.generate_content(prompt)
        raw = response.text.strip()
        raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        quiz = json.loads(raw)

    except Exception as e:
        flash(f"Error generating quiz: {str(e)}")
        return redirect(url_for("student_dashboard"))

    session["quiz"] = quiz
    session["quiz_file"] = filename  

    return render_template("quiz.html", quiz=quiz)

@app.route("/submit_quiz", methods=["POST"])
@login_required(role="student")
def submit_quiz():
    quiz = session.get("quiz")
    if not quiz:
        flash("No quiz found.")
        return redirect(url_for("student_dashboard"))

    score = 0
    results = []

    for i, q in enumerate(quiz, start=1):
        user_answer = (request.form.get(f"q{i}") or "").strip()
        user_letter = user_answer[0].upper() if user_answer else ""
        correct_letter = q["answer"].strip().upper()

        is_correct = (user_letter == correct_letter)

    # Find the full correct option text by matching the letter
        correct_full = next(
        (opt for opt in q["options"] if opt.strip().upper().startswith(correct_letter)),
        correct_letter  # fallback in case nothing matches
        )

        if is_correct:
            score += 1

        results.append({
        "question": q["question"],
        "your_answer": user_answer,    # full text user selected
        "correct_answer": correct_full, # full text correct option
        "is_correct": is_correct
        })


    quiz_id = f"{session.get('quiz_file')}_{int(time.time())}"  
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO quiz_attempts (student_id, quiz_id, score, total, attempted_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user"]["id"],
        quiz_id,
        score,             
        len(quiz),        
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()

    session.pop("quiz", None)
    session.pop("quiz_file", None)

    return render_template("quiz_results.html", score=score, total=len(quiz), results=results)

# ---------- Teacher Dashboard ----------
@app.route("/dashboard/teacher")
@login_required(role="teacher")
def teacher_dashboard():
    user = session.get("user")
    return render_template("teacher_dashboard.html", name=user.get("name"))


@app.route("/upload_books", methods=["GET", "POST"])
@login_required(role="teacher")
def upload_books():
    if request.method == "POST":
        if "book" not in request.files:
            flash("No file selected")
            return redirect(request.url)
        file = request.files["book"]
        if file.filename.endswith(".pdf"):
            filepath = os.path.join(BOOKS_FOLDER, file.filename)
            file.save(filepath)
            flash("Book uploaded successfully!")
            return redirect(url_for("upload_books"))
        else:
            flash("Only PDF files allowed!")
            return redirect(request.url)

    all_books = sorted(
        [f for f in os.listdir(BOOKS_FOLDER) if f.lower().endswith(".pdf")],
        key=lambda x: os.path.getmtime(os.path.join(BOOKS_FOLDER, x)),
        reverse=True
    )
    return render_template("upload_books.html", books=all_books)


@app.route("/student_progress")
@login_required(role="teacher")
def student_progress():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM students")
    students = cur.fetchall()
    
    progress_data = []
    for student in students:
        student_id = student["id"]
        
        # Uploaded textbooks
        cur.execute("SELECT * FROM uploads WHERE student_id = ?", (student_id,))
        uploads = cur.fetchall()
        total_uploads = len(uploads)
        
        # Flashcards
        cur.execute("SELECT * FROM flashcards WHERE student_id = ?", (student_id,))
        flashcards = cur.fetchall()
        total_flashcards = sum(f['num_flashcards'] for f in flashcards)
        
        # Quiz attempts
        cur.execute("SELECT * FROM quiz_attempts WHERE student_id = ?", (student_id,))
        quizzes = cur.fetchall()
        total_quizzes = len(quizzes)
        avg_score = round(sum(q['score'] for q in quizzes) / total_quizzes, 2) if total_quizzes else 0
        completion_rate = f"{total_quizzes}/{total_uploads}" if total_uploads else "0/0"
        
        # Reading / Listening stats
        num_audiobooks = len([u for u in uploads if u['filename'].endswith('.mp3')])
        
        progress_data.append({
            "student": student,
            "uploads": uploads,
            "total_uploads": total_uploads,
            "flashcards": flashcards,
            "total_flashcards": total_flashcards,
            "quizzes": quizzes,
            "total_quizzes": total_quizzes,
            "avg_score": avg_score,
            "completion_rate": completion_rate,
            "num_audiobooks": num_audiobooks
        })
    
    conn.close()
    
    return render_template("student_progress.html", progress_data=progress_data)

# ---------- Logout ----------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("index"))

# ---------- Run ----------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)