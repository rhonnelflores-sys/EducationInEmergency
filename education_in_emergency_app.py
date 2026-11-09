import os
import io
import re
import datetime
import base64
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from werkzeug.security import generate_password_hash, check_password_hash
from docx import Document

# ==============================================================================
# FLASK & DATABASE INITIALIZATION
# ==============================================================================
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'super-secret-tle-key-change-in-production'

CORS(app)
jwt = JWTManager(app)
db = SQLAlchemy(app)

# ==============================================================================
# DATABASE MODELS (SQLAlchemy Schema)
# ==============================================================================
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')
    full_name = db.Column(db.String(120), nullable=True)
    grade = db.Column(db.String(50), nullable=True)
    section = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    quiz_scores = db.relationship('QuizScore', backref='student', lazy=True, cascade="all, delete-orphan")
    rubric_assessments = db.relationship('RubricAssessment', backref='student', lazy=True, cascade="all, delete-orphan")
    reflections = db.relationship('ProjectReflection', backref='student', lazy=True, cascade="all, delete-orphan")
    module_progress = db.relationship('ModuleProgress', backref='student', lazy=True, cascade="all, delete-orphan")
    comments = db.relationship('TeacherComment', backref='student', lazy=True, cascade="all, delete-orphan")

class LearningModule(db.Model):
    __tablename__ = 'learning_modules'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    outcome = db.Column(db.Text, nullable=True)
    activity = db.Column(db.Text, nullable=True)
    reflection = db.Column(db.Text, nullable=True)
    reading = db.Column(db.Text, nullable=True)
    file_name = db.Column(db.String(255), nullable=True)
    file_data = db.Column(db.Text, nullable=True)

class ModuleProgress(db.Model):
    __tablename__ = 'module_progress'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('learning_modules.id'), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class PblProject(db.Model):
    __tablename__ = 'pbl_projects'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    question = db.Column(db.Text, nullable=False)
    product = db.Column(db.Text, nullable=False)

class QuizQuestion(db.Model):
    __tablename__ = 'quiz_questions'
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON, nullable=False)
    correct_key = db.Column(db.Integer, nullable=False)

class QuizScore(db.Model):
    __tablename__ = 'quiz_scores'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    answered = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class RubricCriterion(db.Model):
    __tablename__ = 'rubric_criteria'
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(200), nullable=False)
    max_points = db.Column(db.Integer, default=4)

class RubricAssessment(db.Model):
    __tablename__ = 'rubric_assessments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    scores = db.Column(db.JSON, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    max_possible = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class ProjectReflection(db.Model):
    __tablename__ = 'project_reflections'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    problem = db.Column(db.Text, nullable=True)
    build = db.Column(db.Text, nullable=True)
    improve = db.Column(db.Text, nullable=True)
    next_step = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class TeacherComment(db.Model):
    __tablename__ = 'teacher_comments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    comment_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class SystemConfig(db.Model):
    __tablename__ = 'system_config'
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.Text, nullable=False)

# ==============================================================================
# SYSTEM SEEDING & DATABASE CREATION
# ==============================================================================
def seed_default_data():
    if not db.session.get(SystemConfig, 'appTitle'):
        db.session.add(SystemConfig(key='appTitle', value='TLE Electrical Learning Laboratory'))
    
    if not User.query.filter_by(username='admin').first():
        teacher = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            role='teacher',
            full_name='Lead Instructor'
        )
        db.session.add(teacher)

    if LearningModule.query.count() == 0:
        db.session.add_all([
            LearningModule(
                title='1. Electrical safety and symbols',
                outcome='Identify common electrical hazards, safe working practices, and basic circuit symbols.',
                activity='Learners classify safe and unsafe classroom scenarios and match symbols to component names.',
                reflection='Explain why a virtual simulation should be completed before a supervised practical activity.',
                reading='Electrical safety is paramount. Always ensure low-voltage DC setups are used during early learning.'
            ),
            LearningModule(
                title='2. Circuit parts and functions',
                outcome='Describe the roles of a source, conductor, control device, and load.',
                activity='Build a battery-switch-lamp model and label each component.',
                reflection='Predict what happens when a component or connection is removed.',
                reading='A complete circuit requires four basic parts: Energy Source (Battery), Conductor (Wires), Control Device (Switch), and Load (Lamp/LED).'
            )
        ])

    if PblProject.query.count() == 0:
        db.session.add_all([
            PblProject(title='Grade 7 • Component Explorer', question='Explain the job of each part in a circuit.', product='Labeled circuit & guide.'),
            PblProject(title='Grade 8 • Lamp Control Challenge', question='How does a switch control a load?', product='Build battery-switch-lamp circuit.')
        ])

    if QuizQuestion.query.count() == 0:
        db.session.add_all([
            QuizQuestion(question='What is the main function of a battery in a simple DC circuit?', options=['Provide electrical energy', 'Stop current permanently', 'Measure resistance', 'Open the switch'], correct_key=0),
            QuizQuestion(question='A circuit is closed when…', options=['There is a complete conducting path', 'The switch is always open', 'The battery is removed', 'There are no loads'], correct_key=0),
            QuizQuestion(question='Which component controls whether a path is open or closed?', options=['Lamp', 'Switch', 'Resistor', 'Wire insulation'], correct_key=1),
            QuizQuestion(question='What is the unit of voltage?', options=['Ampere', 'Ohm', 'Volt', 'Watt'], correct_key=2),
            QuizQuestion(question='What is the unit of resistance?', options=['Ohm', 'Volt', 'Ampere', 'Coulomb'], correct_key=0)
        ])

    if RubricCriterion.query.count() == 0:
        db.session.add_all([
            RubricCriterion(label='Circuit completeness', max_points=4),
            RubricCriterion(label='Electrical concept understanding', max_points=4),
            RubricCriterion(label='Testing & evidence', max_points=4),
            RubricCriterion(label='Teamwork', max_points=4),
            RubricCriterion(label='Communication', max_points=4)
        ])

    db.session.commit()

# Ensure tables exist at startup
with app.app_context():
    db.create_all()
    seed_default_data()

# ==============================================================================
# REST API ENDPOINTS
# ==============================================================================
@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"msg": "Invalid username or passcode"}), 401

    access_token = create_access_token(identity=str(user.id), additional_claims={"role": user.role, "name": user.full_name})
    return jsonify({"token": access_token, "role": user.role, "name": user.full_name, "username": user.username})

@app.route('/api/auth/register-student', methods=['POST'])
def register_student():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    grade = data.get('grade', 'Grade 7')
    section = (data.get('section') or 'Section A').strip()

    if not name:
        return jsonify({"msg": "Student name is required"}), 400

    clean_name = re.sub(r'[^a-zA-Z0-9]', '', name.lower())
    clean_sec = re.sub(r'[^a-zA-Z0-9]', '', section.lower())
    username = f"{clean_name}_{clean_sec}" if clean_sec else clean_name

    user = User.query.filter_by(username=username).first()
    
    if not user:
        user = User(
            username=username,
            password_hash=generate_password_hash('student123'),
            role='student',
            full_name=name,
            grade=grade,
            section=section
        )
        db.session.add(user)
        db.session.commit()
    else:
        user.full_name = name
        user.grade = grade
        user.section = section
        db.session.commit()

    token = create_access_token(identity=str(user.id), additional_claims={"role": "student", "name": user.full_name})
    return jsonify({"token": token, "student_id": user.id, "name": user.full_name, "username": user.username})

@app.route('/api/config', methods=['GET', 'POST'])
def config():
    if request.method == 'POST':
        data = request.json or {}
        title = data.get('appTitle')
        if title:
            cfg = db.session.get(SystemConfig, 'appTitle')
            if not cfg:
                cfg = SystemConfig(key='appTitle', value=title)
                db.session.add(cfg)
            else:
                cfg.value = title
            db.session.commit()
            return jsonify({"msg": "Title updated successfully"})
    cfg = db.session.get(SystemConfig, 'appTitle')
    return jsonify({"appTitle": cfg.value if cfg else "TLE Electrical Learning Laboratory"})

@app.route('/api/modules', methods=['GET', 'POST'])
def handle_modules():
    if request.method == 'POST':
        data = request.json or {}
        mod = LearningModule(
            title=data.get('title'),
            outcome=data.get('outcome'),
            activity=data.get('activity'),
            reflection=data.get('reflection'),
            reading=data.get('reading'),
            file_name=data.get('fileName'),
            file_data=data.get('fileData')
        )
        db.session.add(mod)
        db.session.commit()
        return jsonify({"msg": "Module created successfully", "id": mod.id})

    modules = LearningModule.query.all()
    return jsonify([{
        "id": m.id, "title": m.title, "outcome": m.outcome,
        "activity": m.activity, "reflection": m.reflection,
        "reading": m.reading, "fileName": m.file_name, "fileData": m.file_data
    } for m in modules])

@app.route('/api/modules/<int:mod_id>', methods=['DELETE'])
def delete_module(mod_id):
    mod = db.session.get(LearningModule, mod_id)
    if not mod:
        return jsonify({"msg": "Module not found"}), 404
    db.session.delete(mod)
    db.session.commit()
    return jsonify({"msg": "Module deleted successfully"})

@app.route('/api/progress', methods=['GET', 'POST'])
@jwt_required()
def handle_progress():
    user_id = get_jwt_identity()
    if request.method == 'POST':
        data = request.json or {}
        module_id = data.get('module_id')
        completed = data.get('completed', True)
        prog = ModuleProgress.query.filter_by(student_id=user_id, module_id=module_id).first()
        if not prog:
            prog = ModuleProgress(student_id=user_id, module_id=module_id, completed=completed)
            db.session.add(prog)
        else:
            prog.completed = completed
        db.session.commit()
        return jsonify({"msg": "Progress updated"})

    progress = ModuleProgress.query.filter_by(student_id=user_id).all()
    return jsonify({p.module_id: p.completed for p in progress})

@app.route('/api/projects', methods=['GET', 'POST'])
def handle_projects():
    if request.method == 'POST':
        data = request.json or {}
        proj = PblProject(title=data.get('title'), question=data.get('question'), product=data.get('product'))
        db.session.add(proj)
        db.session.commit()
        return jsonify({"msg": "Project added", "id": proj.id})

    projects = PblProject.query.all()
    return jsonify([{"id": p.id, "title": p.title, "question": p.question, "product": p.product} for p in projects])

@app.route('/api/projects/<int:proj_id>', methods=['DELETE'])
def delete_project(proj_id):
    proj = db.session.get(PblProject, proj_id)
    if not proj:
        return jsonify({"msg": "Project not found"}), 404
    db.session.delete(proj)
    db.session.commit()
    return jsonify({"msg": "Project deleted successfully"})

@app.route('/api/quiz', methods=['GET', 'POST'])
def handle_quiz():
    if request.method == 'POST':
        data = request.json or {}
        q = QuizQuestion(question=data.get('q'), options=data.get('opts'), correct_key=int(data.get('key', 0)))
        db.session.add(q)
        db.session.commit()
        return jsonify({"msg": "Quiz question added", "id": q.id})

    questions = QuizQuestion.query.all()
    return jsonify([{"id": q.id, "q": q.question, "opts": q.options, "key": q.correct_key} for q in questions])

@app.route('/api/quiz/<int:q_id>', methods=['DELETE'])
def delete_quiz_question(q_id):
    q = db.session.get(QuizQuestion, q_id)
    if not q:
        return jsonify({"msg": "Question not found"}), 404
    db.session.delete(q)
    db.session.commit()
    return jsonify({"msg": "Question deleted"})

@app.route('/api/quiz/submit', methods=['POST'])
@jwt_required()
def submit_quiz():
    user_id = get_jwt_identity()
    data = request.json or {}
    score_rec = QuizScore(student_id=user_id, score=data.get('score'), total=data.get('total'), answered=data.get('answered'))
    db.session.add(score_rec)
    db.session.commit()
    return jsonify({"msg": "Score submitted successfully"})

@app.route('/api/rubric/criteria', methods=['GET', 'POST'])
def rubric_criteria():
    if request.method == 'POST':
        data = request.json or {}
        c = RubricCriterion(label=data.get('label'), max_points=int(data.get('max', 4)))
        db.session.add(c)
        db.session.commit()
        return jsonify({"msg": "Rubric criterion added", "id": c.id})

    criteria = RubricCriterion.query.all()
    return jsonify([{"id": c.id, "label": c.label, "max": c.max_points} for c in criteria])

@app.route('/api/rubric/criteria/<int:c_id>', methods=['DELETE'])
def delete_rubric_criterion(c_id):
    c = db.session.get(RubricCriterion, c_id)
    if not c:
        return jsonify({"msg": "Criterion not found"}), 404
    db.session.delete(c)
    db.session.commit()
    return jsonify({"msg": "Criterion deleted"})

@app.route('/api/rubric/assess', methods=['POST'])
@jwt_required()
def submit_rubric():
    user_id = get_jwt_identity()
    data = request.json or {}
    assessment = RubricAssessment(
        student_id=user_id, scores=data.get('scores'),
        total=data.get('total'), max_possible=data.get('maxPossible'), notes=data.get('notes')
    )
    db.session.add(assessment)
    db.session.commit()
    return jsonify({"msg": "Rubric assessment saved"})

@app.route('/api/reflections', methods=['POST'])
@jwt_required()
def submit_reflection():
    user_id = get_jwt_identity()
    data = request.json or {}
    ref = ProjectReflection(
        student_id=user_id, title=data.get('title'), problem=data.get('problem'),
        build=data.get('build'), improve=data.get('improve'), next_step=data.get('next')
    )
    db.session.add(ref)
    db.session.commit()
    return jsonify({"msg": "Reflection saved"})

@app.route('/api/upload-docx', methods=['POST'])
def parse_docx():
    if 'file' not in request.files:
        return jsonify({"msg": "No file uploaded"}), 400

    file = request.files['file']
    doc = Document(io.BytesIO(file.read()))
    questions = []
    current_q = None

    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        
        is_q = re.match(r'^\d+[\.\)]\s*(.+)', text)
        is_opt = re.match(r'^[A-Da-d][\.\)]\s*(.+)', text)

        if is_q:
            if current_q and len(current_q['opts']) >= 2:
                questions.append(current_q)
            current_q = {'q': is_q.group(1), 'opts': [], 'key': 0}
        elif is_opt and current_q:
            current_q['opts'].append(is_opt.group(1))
        elif current_q and len(current_q['opts']) == 0:
            current_q['q'] += " " + text

    if current_q and len(current_q['opts']) >= 2:
        questions.append(current_q)

    replace = request.form.get('replace') == 'true'
    if replace:
        QuizQuestion.query.delete()

    for q in questions:
        db.session.add(QuizQuestion(question=q['q'], options=q['opts'], correct_key=q['key']))
    db.session.commit()

    return jsonify({"msg": f"Successfully imported {len(questions)} questions.", "count": len(questions)})

@app.route('/api/dashboard', methods=['GET'])
def dashboard_data():
    students = User.query.filter_by(role='student').all()
    modules_count = LearningModule.query.count()
    records = []
    total_score = 0
    score_count = 0

    for s in students:
        last_score = QuizScore.query.filter_by(student_id=s.id).order_by(QuizScore.created_at.desc()).first()
        last_rubric = RubricAssessment.query.filter_by(student_id=s.id).order_by(RubricAssessment.created_at.desc()).first()
        reflections_count = ProjectReflection.query.filter_by(student_id=s.id).count()
        progress_count = ModuleProgress.query.filter_by(student_id=s.id, completed=True).count()
        comments = TeacherComment.query.filter_by(student_id=s.id).order_by(TeacherComment.created_at.asc()).all()

        if last_score and last_score.total > 0:
            total_score += (last_score.score / last_score.total) * 100
            score_count += 1

        records.append({
            "id": s.id, "name": s.full_name, "grade": s.grade,
            "section": s.section or 'Unassigned',
            "quiz": f"{last_score.score}/{last_score.total}" if last_score else "—",
            "rubric": f"{last_rubric.total}/{last_rubric.max_possible}" if last_rubric else "—",
            "modules": f"{progress_count}/{modules_count}",
            "projects": reflections_count,
            "comments": [{"text": c.comment_text, "date": c.created_at.strftime("%Y-%m-%d %H:%M")} for c in comments]
        })

    avg = (total_score / score_count) if score_count > 0 else 0

    return jsonify({
        "studentCount": len(students),
        "avgScore": f"{avg:.1f}%" if score_count > 0 else "—",
        "projectsDone": ProjectReflection.query.count(),
        "records": records
    })

@app.route('/api/comments', methods=['POST'])
def add_comment():
    data = request.json or {}
    comment = TeacherComment(student_id=data.get('student_id'), comment_text=data.get('text'))
    db.session.add(comment)
    db.session.commit()
    return jsonify({"msg": "Comment added"})

# ==============================================================================
# SINGLE-PAGE FRONTEND APPLICATION (HTML/CSS/JS)
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title id="appDocTitle">TLE Electrical Learning Laboratory</title>
<style>
:root{--navy:#14243a;--blue:#2563eb;--cyan:#0ea5a4;--bg:#f3f6fb;--card:#fff;--ink:#172033;--muted:#64748b;--line:#dce4ef;--good:#15803d;--warn:#b45309;--bad:#b91c1c}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--ink)}
header{background:linear-gradient(115deg,#14243a,#1d4e89);color:#fff;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap}
header h1{font-size:24px;margin:0}header p{margin:4px 0 0;color:#dbeafe;font-size:13px}
.wrap{max-width:1400px;margin:auto;padding:16px 24px 40px}
.tabs{display:flex;gap:8px;margin-bottom:16px;overflow-x:auto}.tab{border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:8px;padding:8px 16px;cursor:pointer;font-weight:600}.tab.active{background:var(--navy);color:#fff}
.panel{display:none}.panel.active{display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px;box-shadow:0 2px 6px #13233a05}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:12px}.span-3{grid-column:span 3}.span-4{grid-column:span 4}.span-5{grid-column:span 5}.span-6{grid-column:span 6}.span-7{grid-column:span 7}.span-8{grid-column:span 8}.span-12{grid-column:span 12}
@media(max-width:800px){.span-3,.span-4,.span-5,.span-6,.span-7,.span-8{grid-column:span 12}}
label{display:block;font-weight:600;margin:6px 0 2px;font-size:13px}input,select,textarea{width:100%;padding:9px;border:1px solid #cbd5e1;border-radius:6px;font:inherit}textarea{min-height:75px}
.btn{border:0;border-radius:6px;padding:9px 14px;background:var(--blue);color:#fff;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:6px}.btn.secondary{background:#e8eef8;color:#19314f}.btn.danger{background:var(--bad)}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.sim-layout{display:grid;grid-template-columns:240px 1fr;gap:12px}@media(max-width:800px){.sim-layout{grid-template-columns:1fr}}
.parts{display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:6px}.part{border:1px solid var(--line);border-radius:6px;padding:8px;background:#fbfdff;cursor:pointer;text-align:center}
.board{background:#f8fbff;border:1px solid #d8e3f0;border-radius:8px;overflow:hidden}.board svg{width:100%;height:360px;display:block}
.terminal{fill:#fff;stroke:#2563eb;stroke-width:3;cursor:pointer}.wire{stroke:#64748b;stroke-width:4;fill:none}.wire.live{stroke:#16a34a;stroke-dasharray:8 4;animation:flow 1s linear infinite}@keyframes flow{to{stroke-dashoffset:-12}}
.part-shape{stroke:#1e293b;stroke-width:2;fill:#fff}.part-label{font-size:13px;fill:#172033;font-weight:600;text-anchor:middle}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:8px;border-bottom:1px solid var(--line);text-align:left}th{background:#f8fafc}
.modal-overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(20,36,58,0.7);z-index:9999;align-items:center;justify-content:center}
.modal-overlay.active{display:flex}.modal{background:#fff;padding:20px;border-radius:12px;max-width:400px;width:100%}
.pill{display:inline-block;border-radius:99px;background:#e8f1ff;color:#1d4ed8;padding:2px 8px;font-size:12px;font-weight:700}
.metric{font-size:24px;font-weight:800}.metric-label{color:var(--muted);font-size:12px}
</style>
</head>
<body>
<header>
 <div>
  <h1 id="appTitleText">⚡ TLE Electrical Learning Laboratory</h1>
  <p>Full-Stack Python + SQL Circuit Learning Platform</p>
 </div>
 <div>
  <span class="pill" id="userBadge">Not Logged In</span>
 </div>
</header>

<div class="wrap">
<nav class="tabs">
 <button class="tab active" onclick="switchTab('sim', this)">Circuit Lab</button>
 <button class="tab" onclick="switchTab('learn', this)">Modules</button>
 <button class="tab" onclick="switchTab('projects', this)">PBL Projects</button>
 <button class="tab" onclick="switchTab('assess', this)">Quiz & Rubric</button>
 <button class="tab" onclick="switchTab('teacher', this)">🔒 Teacher Dashboard</button>
</nav>

<!-- SIMULATOR PANEL -->
<section class="panel active" id="sim">
 <div class="card">
  <h2>Student Session</h2>
  <div class="grid">
   <div class="span-4"><label>Full Name</label><input id="studentName" placeholder="Enter full name"></div>
   <div class="span-4"><label>Grade Level</label><select id="grade"><option>Grade 7</option><option>Grade 8</option><option>Grade 9</option><option>Grade 10</option></select></div>
   <div class="span-4"><label>Section</label><input id="section" placeholder="e.g. Section Mabini"></div>
  </div>
  <div class="actions"><button class="btn" onclick="saveStudentSession()">Register / Initialize Session</button></div>
 </div>

 <div class="sim-layout">
  <div class="card">
   <h3>Toolbox</h3>
   <div class="parts">
    <button class="part" onclick="addPart('battery')">🔋 Battery</button>
    <button class="part" onclick="addPart('switch')">⏻ Switch</button>
    <button class="part" onclick="addPart('lamp')">💡 Lamp</button>
    <button class="part" onclick="addPart('resistor')">▱ Resistor</button>
   </div>
   <div style="margin-top:10px">
    <label>Battery Volts</label>
    <input id="batteryVoltage" type="range" min="1" max="12" value="6" oninput="$('vLabel').textContent=this.value+' V'">
    <div style="text-align:right"><b id="vLabel">6 V</b></div>
   </div>
   <div class="actions">
    <button class="btn secondary" id="wireBtn" onclick="toggleWireMode()">🔌 Wire Mode</button>
    <button class="btn danger" onclick="resetBoard()">Reset</button>
   </div>
  </div>

  <div class="card">
   <div class="board"><svg id="circuit" viewBox="0 0 900 360"></svg></div>
   <div class="actions">
    <button class="btn" onclick="runSim()">▶ Test Circuit</button>
    <button class="btn secondary" onclick="stopSim()">Stop</button>
   </div>
   <div class="grid" style="margin-top:10px">
    <div class="span-3 card"><div class="metric" id="readVoltage">0.00 V</div><div class="metric-label">Voltage</div></div>
    <div class="span-3 card"><div class="metric" id="readCurrent">0.00 A</div><div class="metric-label">Current</div></div>
    <div class="span-3 card"><div class="metric" id="readResistance">— Ω</div><div class="metric-label">Resistance</div></div>
    <div class="span-3 card"><div class="metric" id="readState">OFF</div><div class="metric-label">Status</div></div>
   </div>
  </div>
 </div>
</section>

<!-- MODULES PANEL -->
<section class="panel" id="learn">
 <div class="card"><h2>Learning Modules</h2><div id="modulesList"></div></div>
</section>

<!-- PBL PROJECTS PANEL -->
<section class="panel" id="projects">
 <div class="card"><h2>Project-Based Learning Activities</h2><div id="projectList"></div></div>
 <div class="card">
  <h3>Submit Project Reflection</h3>
  <label>Project Title</label><input id="refTitle">
  <label>Problem Addressed</label><textarea id="refProblem"></textarea>
  <label>Built Design</label><textarea id="refBuild"></textarea>
  <label>Improvements</label><textarea id="refImprove"></textarea>
  <label>Next Steps</label><textarea id="refNext"></textarea>
  <div class="actions"><button class="btn" onclick="submitReflection()">Submit Reflection</button></div>
 </div>
</section>

<!-- QUIZ & RUBRIC PANEL -->
<section class="panel" id="assess">
 <div class="grid">
  <div class="card span-7">
   <h2>Quiz Assessment</h2>
   <form id="quizForm"><div id="quizContainer"></div><button class="btn" type="submit" style="margin-top:10px">Submit Quiz</button></form>
  </div>
  <div class="card span-5">
   <h2>Project Rubric</h2>
   <div id="rubricContainer"></div>
   <div class="metric" id="rubricTotal">0 / 20</div>
   <label>Teacher Notes</label><textarea id="rubricNotes"></textarea>
   <div class="actions"><button class="btn" onclick="submitRubric()">Save Evaluation</button></div>
  </div>
 </div>
</section>

<!-- TEACHER DASHBOARD PANEL -->
<section class="panel" id="teacher">
 <div class="card">
  <h2>✏️ Global Program Title Settings</h2>
  <div class="grid">
   <div class="span-8"><input id="titleEditInput"></div>
   <div class="span-4"><button class="btn" onclick="updateTitle()">Save Title</button></div>
  </div>
 </div>

 <div class="card">
  <h2>📖 Teacher Module & Reading Material Manager</h2>
  <p style="color:var(--muted);font-size:13px">Add reading materials, instructional modules, and downloadable attachments for students.</p>
  <div class="grid">
   <div class="span-6"><label>Module Title</label><input id="modTitle" placeholder="e.g. 3. Ohm's Law Fundamentals"></div>
   <div class="span-6"><label>Learning Outcome</label><input id="modOutcome" placeholder="Key objective..."></div>
   <div class="span-6"><label>Learning Activity</label><input id="modActivity" placeholder="Activity description..."></div>
   <div class="span-6"><label>Reflection / Prompt Question</label><input id="modReflection" placeholder="Reflection topic..."></div>
   <div class="span-12"><label>Reading Material Content</label><textarea id="modReading" placeholder="Detailed reading text or notes for students..."></textarea></div>
   <div class="span-12">
    <label>Attach Optional File (.pdf, .docx, .png, .txt)</label>
    <input type="file" id="modFileInput">
   </div>
  </div>
  <div class="actions"><button class="btn" onclick="createModule()">Create New Module</button></div>
 </div>

 <div class="card">
  <h2>🛠️ PBL Projects Manager</h2>
  <div id="pblAdminList" style="margin-bottom:12px"></div>
  <h3>Add New PBL Project</h3>
  <div class="grid">
   <div class="span-4"><label>Project Title</label><input id="newPblTitle" placeholder="Title"></div>
   <div class="span-4"><label>Essential Question</label><input id="newPblQuestion" placeholder="Question"></div>
   <div class="span-4"><label>Target Product</label><input id="newPblProduct" placeholder="Product"></div>
  </div>
  <div class="actions"><button class="btn" onclick="createProject()">Add PBL Project</button></div>
 </div>

 <div class="card">
  <h2>📁 Student Class Records (SQL Database)</h2>
  <div class="grid" style="margin-bottom:12px">
   <div class="span-4 card"><div class="metric" id="dashStudents">0</div><div class="metric-label">Registered Students</div></div>
   <div class="span-4 card"><div class="metric" id="dashAvg">—</div><div class="metric-label">Average Quiz Score</div></div>
   <div class="span-4 card"><div class="metric" id="dashProjects">0</div><div class="metric-label">Reflections Submitted</div></div>
  </div>
  <table>
   <thead><tr><th>Student</th><th>Grade</th><th>Section</th><th>Quiz Score</th><th>Rubric Total</th><th>Modules</th><th>Comments</th></tr></thead>
   <tbody id="studentTableBody"></tbody>
  </table>
 </div>

 <div class="card">
  <h2>📄 Parse MS Word Quiz (.docx) to Backend DB</h2>
  <input type="file" id="docxInput" accept=".docx">
  <div class="actions"><button class="btn" onclick="uploadDocx()">Upload & Parse Word Doc</button></div>
 </div>
</section>

</div>

<!-- AUTH MODAL -->
<div class="modal-overlay" id="authModal">
 <div class="modal">
  <h2>🔑 Teacher Auth</h2>
  <label>Passcode / Password</label>
  <input type="password" id="teacherPasscode" placeholder="Enter admin password">
  <div class="actions" style="margin-top:12px">
   <button class="btn secondary" onclick="$('authModal').classList.remove('active')">Cancel</button>
   <button class="btn" onclick="loginTeacher()">Login</button>
  </div>
 </div>
</div>

<script>
const $=id=>document.getElementById(id);
let jwtToken = localStorage.getItem('token') || '';
let currentUser = JSON.parse(localStorage.getItem('user') || '{}');

function updateAuthUI() {
 const badge = $('userBadge');
 if (jwtToken && currentUser.name) {
  badge.textContent = `${currentUser.name} (${currentUser.role})`;
 } else {
  badge.textContent = 'Not Logged In';
 }
}

function switchTab(id, btn) {
 if (id === 'teacher' && currentUser.role !== 'teacher') {
  $('authModal').classList.add('active');
  return;
 }
 document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
 document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
 $(id).classList.add('active');
 if(btn) btn.classList.add('active');
 if(id==='learn') loadModules();
 if(id==='projects') loadProjects();
 if(id==='assess') { loadQuiz(); loadRubric(); }
 if(id==='teacher') loadDashboard();
}

async function api(path, method='GET', body=null) {
 const headers = {'Content-Type': 'application/json'};
 if (jwtToken) headers['Authorization'] = `Bearer ${jwtToken}`;
 const opts = { method, headers };
 if (body) opts.body = JSON.stringify(body);
 const res = await fetch('/api' + path, opts);
 return res.json();
}

api('/api/config').then(data => {
 $('appTitleText').textContent = data.appTitle;
 $('titleEditInput').value = data.appTitle;
});

function updateTitle() {
 api('/api/config', 'POST', {appTitle: $('titleEditInput').value}).then(res => {
  $('appTitleText').textContent = $('titleEditInput').value;
  alert(res.msg);
 });
}

async function saveStudentSession() {
 const name = $('studentName').value.trim();
 const grade = $('grade').value;
 const section = $('section').value.trim();
 if (!name) return alert('Enter full name');
 
 localStorage.removeItem('token');
 localStorage.removeItem('user');
 jwtToken = '';

 const res = await fetch('/api/auth/register-student', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({name, grade, section})
 });
 
 const data = await res.json();
 if(res.ok) {
  jwtToken = data.token;
  currentUser = {id: data.student_id, name: data.name, role: 'student'};
  localStorage.setItem('token', jwtToken);
  localStorage.setItem('user', JSON.stringify(currentUser));
  updateAuthUI();
  alert('Session Saved & Authenticated!');
 } else {
  alert(data.msg || 'Registration failed');
 }
}

async function loginTeacher() {
 const pass = $('teacherPasscode').value;
 const res = await fetch('/api/auth/login', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({username: 'admin', password: pass})
 });
 const data = await res.json();
 if (res.ok) {
  jwtToken = data.token;
  currentUser = {name: data.name, role: data.role};
  localStorage.setItem('token', jwtToken);
  localStorage.setItem('user', JSON.stringify(currentUser));
  updateAuthUI();
  $('authModal').classList.remove('active');
  switchTab('teacher');
 } else {
  alert(data.msg);
 }
}

async function loadModules() {
 const mods = await api('/api/modules');
 const prog = jwtToken ? await api('/api/progress') : {};
 $('modulesList').innerHTML = mods.map(m => `
  <div class="card" style="background:#f8fafc">
   <div style="display:flex;justify-content:space-between;align-items:center">
    <h3>${m.title} ${prog[m.id]?'✓':''}</h3>
    ${currentUser.role==='teacher'?`<button class="btn danger" style="padding:4px 8px;font-size:12px" onclick="deleteModule(${m.id})">Delete</button>`:''}
   </div>
   <p><b>Outcome:</b> ${m.outcome || 'N/A'}</p>
   <p><b>Activity:</b> ${m.activity || 'N/A'}</p>
   <p><b>Reading:</b> ${m.reading || 'N/A'}</p>
   ${m.fileName?`<p><b>Attachment:</b> <a href="${m.fileData}" download="${m.fileName}" class="pill">Download ${m.fileName}</a></p>`:''}
   <p><b>Reflection:</b> ${m.reflection || 'N/A'}</p>
   <button class="btn ${prog[m.id]?'secondary':''}" onclick="toggleProgress(${m.id}, ${!prog[m.id]})">${prog[m.id]?'Mark Incomplete':'Mark Complete'}</button>
  </div>
 `).join('');
}

async function createModule() {
 const title = $('modTitle').value.trim();
 if(!title) return alert('Module title is required');
 
 const fileInput = $('modFileInput');
 let fileName = null, fileData = null;

 if(fileInput.files && fileInput.files[0]) {
  const file = fileInput.files[0];
  fileName = file.name;
  fileData = await new Promise((resolve) => {
   const reader = new FileReader();
   reader.onload = e => resolve(e.target.result);
   reader.readAsDataURL(file);
  });
 }

 await api('/api/modules', 'POST', {
  title, outcome: $('modOutcome').value, activity: $('modActivity').value,
  reflection: $('modReflection').value, reading: $('modReading').value,
  fileName, fileData
 });

 $('modTitle').value = $('modOutcome').value = $('modActivity').value = $('modReflection').value = $('modReading').value = $('modFileInput').value = '';
 alert('Module Created Successfully!');
 loadModules();
}

async function deleteModule(id) {
 if(!confirm('Delete this module?')) return;
 await api('/api/modules/' + id, 'DELETE');
 loadModules();
}

async function toggleProgress(id, completed) {
 if (!jwtToken) return alert('Register student session first.');
 await api('/api/progress', 'POST', {module_id: id, completed});
 loadModules();
}

async function loadProjects() {
 const projs = await api('/api/projects');
 $('projectList').innerHTML = projs.map(p => `
  <div class="card" style="background:#f8fafc">
   <h3>${p.title}</h3>
   <p><b>Question:</b> ${p.question}</p>
   <p><b>Deliverable:</b> ${p.product}</p>
  </div>
 `).join('');

 $('pblAdminList').innerHTML = projs.map(p => `
  <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--line)">
   <span><b>${p.title}</b> — ${p.question}</span>
   <button class="btn danger" style="padding:2px 8px;font-size:12px" onclick="deleteProject(${p.id})">Delete</button>
  </div>
 `).join('');
}

async function createProject() {
 const title = $('newPblTitle').value.trim();
 const question = $('newPblQuestion').value.trim();
 const product = $('newPblProduct').value.trim();
 if(!title || !question) return alert('Title and Question are required');

 await api('/api/projects', 'POST', {title, question, product});
 $('newPblTitle').value = $('newPblQuestion').value = $('newPblProduct').value = '';
 alert('PBL Project Added!');
 loadProjects();
}

async function deleteProject(id) {
 if(!confirm('Delete this project?')) return;
 await api('/api/projects/' + id, 'DELETE');
 loadProjects();
}

async function submitReflection() {
 if (!jwtToken) return alert('Register session first');
 await api('/api/reflections', 'POST', {
  title: $('refTitle').value,
  problem: $('refProblem').value,
  build: $('refBuild').value,
  improve: $('refImprove').value,
  next: $('refNext').value
 });
 alert('Reflection submitted to DB!');
}

async function loadQuiz() {
 const qs = await api('/api/quiz');
 $('quizContainer').innerHTML = qs.map((q, i) => `
  <div style="margin-bottom:12px">
   <b>${i+1}. ${q.q}</b>
   ${q.opts.map((o, j) => `<label><input type="radio" name="q${i}" value="${j}"> ${o}</label>`).join('')}
  </div>
 `).join('');
}

$('quizForm').onsubmit = async (e) => {
 e.preventDefault();
 if (!jwtToken) return alert('Register session first');
 const qs = await api('/api/quiz');
 intScore = 0;
 qs.forEach((q, i) => {
  const sel = document.querySelector(`input[name="q${i}"]:checked`);
  if (sel && parseInt(sel.value) === q.key) intScore++;
 });
 await api('/api/quiz/submit', 'POST', {score: intScore, total: qs.length, answered: qs.length});
 alert(`Quiz Submitted! Score: ${intScore}/${qs.length}`);
};

async function loadRubric() {
 const crits = await api('/api/rubric/criteria');
 $('rubricContainer').innerHTML = crits.map((c, i) => `
  <div style="display:flex;justify-content:space-between;margin-bottom:6px">
   <span><b>${c.label}</b> (Max: ${c.max})</span>
   <select class="rScore" data-max="${c.max}">${[...Array(c.max+1).keys()].map(v=>`<option value="${v}">${v}</option>`).join('')}</select>
  </div>
 `).join('');
}

async function submitRubric() {
 if (!jwtToken) return alert('Register session first');
 const scores = [...document.querySelectorAll('.rScore')].map(s=>parseInt(s.value));
 const total = scores.reduce((a,b)=>a+b,0);
 const maxPossible = [...document.querySelectorAll('.rScore')].reduce((a,s)=>a+parseInt(s.dataset.max),0);
 await api('/api/rubric/assess', 'POST', {scores, total, maxPossible, notes: $('rubricNotes').value});
 alert('Evaluation saved to SQL database!');
}

async function loadDashboard() {
 const data = await api('/api/dashboard');
 $('dashStudents').textContent = data.studentCount;
 $('dashAvg').textContent = data.avgScore;
 $('dashProjects').textContent = data.projectsDone;
 
 $('studentTableBody').innerHTML = data.records.map(r => `
  <tr>
   <td><b>${r.name}</b></td>
   <td>${r.grade}</td>
   <td>${r.section}</td>
   <td>${r.quiz}</td>
   <td>${r.rubric}</td>
   <td>${r.modules}</td>
   <td>
    ${r.comments.map(c => `<div><small>${c.date}: ${c.text}</small></div>`).join('')}
    <input id="cmt_${r.id}" placeholder="Add note..." style="width:120px;padding:2px">
    <button class="btn secondary" style="padding:2px 6px;font-size:11px" onclick="addComment(${r.id})">Post</button>
   </td>
  </tr>
 `).join('');

 loadProjects();
}

async function addComment(studentId) {
 const txt = $(`cmt_${studentId}`).value;
 if(!txt) return;
 await api('/api/comments', 'POST', {student_id: studentId, text: txt});
 loadDashboard();
}

async function uploadDocx() {
 const file = $('docxInput').files[0];
 if(!file) return alert('Select a DOCX file first');
 const formData = new FormData();
 formData.append('file', file);
 const res = await fetch('/api/upload-docx', {method: 'POST', body: formData});
 const data = await res.json();
 alert(data.msg);
}

let parts=[], wires=[], wireMode=false, firstTerm=null, running=false;
const svg = $('circuit');

function addPart(type) {
 parts.push({id: Date.now(), type, x: 100 + (parts.length*100)%700, y: 150, value: parseInt($('batteryVoltage').value), closed: true});
 renderSvg();
}
function toggleWireMode() { wireMode = !wireMode; $('wireBtn').classList.toggle('secondary'); }
function resetBoard() { parts=[]; wires=[]; renderSvg(); }

function renderSvg() {
 svg.innerHTML = '';
 wires.forEach(w => {
  const p1 = parts.find(p=>p.id===w.a.id), p2 = parts.find(p=>p.id===w.b.id);
  if(p1 && p2) {
   const x1 = p1.x + (w.a.side===0?-30:30), y1 = p1.y;
   const x2 = p2.x + (w.b.side===0?-30:30), y2 = p2.y;
   svg.insertAdjacentHTML('beforeend', `<line class="wire ${running?'live':''}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`);
  }
 });
 parts.forEach(p => {
  svg.insertAdjacentHTML('beforeend', `
   <g transform="translate(${p.x} ${p.y})">
    <rect x="-40" y="-30" width="80" height="60" rx="6" fill="#fff" stroke="#1e293b" stroke-width="2"/>
    <text x="0" y="5" class="part-label">${p.type.toUpperCase()}</text>
    <circle class="terminal" onclick="termClick(${p.id}, 0)" cx="-30" cy="0" r="5"/>
    <circle class="terminal" onclick="termClick(${p.id}, 1)" cx="30" cy="0" r="5"/>
   </g>
  `);
 });
}

function termClick(id, side) {
 if(!wireMode) return;
 if(!firstTerm) { firstTerm = {id, side}; return; }
 wires.push({a: firstTerm, b: {id, side}});
 firstTerm = null;
 renderSvg();
}

function runSim() {
 running = parts.some(p=>p.type==='battery') && parts.some(p=>p.type==='lamp') && wires.length >= 2;
 $('readState').textContent = running ? 'ON' : 'OFF';
 $('readVoltage').textContent = running ? $('batteryVoltage').value + '.00 V' : '0.00 V';
 $('readCurrent').textContent = running ? '0.60 A' : '0.00 A';
 $('readResistance').textContent = running ? '10.0 Ω' : '— Ω';
 renderSvg();
}
function stopSim() { running = false; $('readState').textContent = 'OFF'; renderSvg(); }

updateAuthUI();
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
