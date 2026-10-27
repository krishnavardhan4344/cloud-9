"""NoteShare - Online Notes Management and Sharing System (Flask backend).

Storage: JSON files in ./data (metadata) and files in ./uploads (documents).
No external database is used.
"""
import json
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "txt", "md"}
VIEWABLE = {"pdf", "txt", "md"}          # shown inline in the browser
MAX_FILE_MB = 10
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
PER_PAGE = 9

DEPARTMENTS = [
    "Computer Science", "Information Technology", "Artificial Intelligence & Data Science",
    "Electronics & Communication", "Electrical & Electronics", "Mechanical Engineering",
    "Civil Engineering", "Chemical Engineering", "Biomedical Engineering",
    "Mathematics", "Physics", "Chemistry", "English", "Management Studies", "Other",
]
SEMESTERS = list(range(1, 9))

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --------------------------------------------------------------------------
# JSON storage (thread-safe, atomic writes)
# --------------------------------------------------------------------------
class JsonStore:
    """A tiny JSON-file 'table' holding a list of dict records."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def _read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            backup = self.path.with_suffix(f".corrupt-{int(time.time())}")
            os.replace(self.path, backup)      # keep the bad file, start clean
            return []

    def _write(self, data):
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)             # atomic on Windows and Linux

    def all(self):
        with self.lock:
            return self._read()

    def transaction(self, fn):
        """Run fn(records) under a lock; the (mutated) list is saved afterwards.
        If fn raises, nothing is written."""
        with self.lock:
            data = self._read()
            result = fn(data)
            self._write(data)
            return result


# --------------------------------------------------------------------------
# Domain helpers
# --------------------------------------------------------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_user(users, username, email, password, role="student"):
    def txn(data):
        for u in data:
            if u["username"].lower() == username.lower():
                raise ValueError("That username is already taken.")
            if u["email"].lower() == email.lower():
                raise ValueError("That email address is already registered.")
        user = {
            "id": uuid.uuid4().hex,
            "username": username,
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": role,
            "created_at": now_iso(),
        }
        data.append(user)
        return user
    return users.transaction(txn)


def content_matches(ext, data):
    """Check the file's real content against its extension (magic bytes)."""
    if ext == "pdf":
        return data[:1024].lstrip().startswith(b"%PDF-")
    if ext in ("docx", "pptx"):
        return data.startswith(b"PK\x03\x04")
    if ext in ("doc", "ppt"):
        return data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if ext in ("txt", "md"):
        if b"\x00" in data:
            return False
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    return False


def validate_upload(file):
    """Return (safe_display_name, ext, bytes) or raise ValueError."""
    if file is None or not file.filename:
        raise ValueError("Please choose a file to upload.")
    original = file.filename.replace("\\", "/").split("/")[-1].strip()
    if not original or len(original) > 150 or any(ord(c) < 32 for c in original):
        raise ValueError("Invalid file name.")
    if "." not in original:
        raise ValueError("The file must have an extension such as .pdf or .docx.")
    stem, ext = original.rsplit(".", 1)
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("File type .%s is not allowed. Allowed types: %s."
                         % (ext[:10], ", ".join(sorted(ALLOWED_EXTENSIONS))))
    data = file.read(MAX_FILE_BYTES + 1)
    if not data:
        raise ValueError("The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("File is too large. The maximum size is %d MB." % MAX_FILE_MB)
    if not content_matches(ext, data):
        raise ValueError("The file content does not match its .%s extension." % ext)
    return "%s.%s" % (secure_filename(stem) or "note", ext), ext, data


def store_note(notes, upload_dir, *, title, description, subject, department,
               semester, original_name, ext, data, user):
    stored_name = "%s.%s" % (uuid.uuid4().hex, ext)
    path = Path(upload_dir) / stored_name
    path.write_bytes(data)
    note = {
        "id": uuid.uuid4().hex,
        "title": title, "description": description, "subject": subject,
        "department": department, "semester": semester,
        "original_name": original_name, "stored_name": stored_name, "ext": ext,
        "size": len(data), "downloads": 0,
        "uploader_id": user["id"], "uploader_name": user["username"],
        "uploaded_at": now_iso(),
    }
    try:
        notes.transaction(lambda d: d.append(note))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return note


def remove_notes(notes, upload_dir, predicate):
    """Delete every note matching predicate (record + file). Returns count."""
    removed = []

    def txn(data):
        keep = []
        for n in data:
            (removed if predicate(n) else keep).append(n)
        data[:] = keep
    notes.transaction(txn)
    for n in removed:
        (Path(upload_dir) / n["stored_name"]).unlink(missing_ok=True)
    return len(removed)


def safe_next(target, default):
    """Only allow local relative redirects (blocks open-redirect attacks)."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return default


def filter_notes(notes, args, user):
    q = args.get("q", "").strip().lower()
    dept = args.get("department", "").strip()
    subject = args.get("subject", "").strip().lower()
    ftype = args.get("type", "").strip().lower()
    sem = args.get("semester", "").strip()
    mine = args.get("mine") == "1" and user is not None
    out = []
    for n in notes:
        if mine and n["uploader_id"] != user["id"]:
            continue
        if dept and n["department"] != dept:
            continue
        if subject and n["subject"].lower() != subject:
            continue
        if ftype and n["ext"] != ftype:
            continue
        if sem and str(n.get("semester") or "") != sem:
            continue
        if q:
            hay = " ".join([n["title"], n["subject"], n["department"], n["description"],
                            n["uploader_name"], n["original_name"]]).lower()
            if q not in hay:
                continue
        out.append(n)
    sort = args.get("sort", "newest")
    if sort == "oldest":
        out.sort(key=lambda n: n["uploaded_at"])
    elif sort == "title":
        out.sort(key=lambda n: n["title"].lower())
    elif sort == "downloads":
        out.sort(key=lambda n: (-n["downloads"], n["title"].lower()))
    else:
        out.sort(key=lambda n: n["uploaded_at"], reverse=True)
    return out


# --------------------------------------------------------------------------
# Application factory
# --------------------------------------------------------------------------
def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        DATA_DIR=BASE_DIR / "data",
        UPLOAD_DIR=BASE_DIR / "uploads",
        MAX_CONTENT_LENGTH=MAX_FILE_BYTES + 1024 * 1024,   # form overhead allowance
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME", "admin"),
        ADMIN_EMAIL=os.environ.get("ADMIN_EMAIL", "admin@example.com"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "Admin@12345"),
        LOGIN_MAX_ATTEMPTS=5,
        LOGIN_WINDOW_SECONDS=300,
    )
    if config:
        app.config.update(config)

    data_dir = Path(app.config["DATA_DIR"])
    upload_dir = Path(app.config["UPLOAD_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Secret key: env var, else a random key persisted in data/secret.key
    key_file = data_dir / "secret.key"
    if os.environ.get("SECRET_KEY"):
        app.secret_key = os.environ["SECRET_KEY"]
    else:
        if not key_file.exists():
            key_file.write_text(secrets.token_hex(32))
        app.secret_key = key_file.read_text().strip()

    users = JsonStore(data_dir / "users.json")
    notes = JsonStore(data_dir / "notes.json")
    app.users, app.notes, app.upload_dir = users, notes, upload_dir

    # Create the default administrator on first run
    if not any(u["role"] == "admin" for u in users.all()):
        create_user(users, app.config["ADMIN_USERNAME"], app.config["ADMIN_EMAIL"],
                    app.config["ADMIN_PASSWORD"], role="admin")

    failed_logins = {}
    failed_lock = threading.Lock()

    # ---- template helpers -------------------------------------------------
    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return session["_csrf"]

    def page_url(page):
        args = request.args.to_dict()
        args["page"] = page
        return url_for("notes_list", **args)

    app.jinja_env.globals.update(
        csrf_token=csrf_token, page_url=page_url, viewable=VIEWABLE,
        departments=DEPARTMENTS, semesters=SEMESTERS, allowed_exts=sorted(ALLOWED_EXTENSIONS),
        max_mb=MAX_FILE_MB)

    @app.template_filter("filesize")
    def filesize(n):
        n = float(n)
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024 or unit == "GB":
                return "%d B" % n if unit == "B" else "%.1f %s" % (n, unit)
            n /= 1024

    @app.template_filter("datefmt")
    def datefmt(iso):
        try:
            return datetime.fromisoformat(iso).strftime("%d %b %Y")
        except (TypeError, ValueError):
            return ""

    # ---- request hooks ----------------------------------------------------
    @app.before_request
    def load_user():
        g.user = None
        uid = session.get("user_id")
        if uid:
            g.user = next((u for u in users.all() if u["id"] == uid), None)
            if g.user is None:
                session.clear()

    @app.before_request
    def csrf_protect():
        if request.method == "POST":
            sent = request.form.get("_csrf", "")
            expected = session.get("_csrf", "")
            if not expected or not sent or not secrets.compare_digest(sent, expected):
                abort(400)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.endpoint != "view_note":     # PDF viewers need a relaxed policy
            resp.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; object-src 'none'; "
                "frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
        if g.get("user"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    def login_required(view):
        @wraps(view)
        def wrapped(*a, **kw):
            if g.user is None:
                flash("Please log in to continue.", "error")
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            return view(*a, **kw)
        return wrapped

    def admin_required(view):
        @wraps(view)
        @login_required
        def wrapped(*a, **kw):
            if g.user["role"] != "admin":
                abort(403)
            return view(*a, **kw)
        return wrapped

    def get_note_or_404(note_id):
        note = next((n for n in notes.all() if n["id"] == note_id), None)
        if note is None:
            abort(404)
        return note

    # ---- public pages & auth ---------------------------------------------
    @app.route("/")
    def index():
        all_notes = notes.all()
        recent = sorted(all_notes, key=lambda n: n["uploaded_at"], reverse=True)[:3]
        stats = {"notes": len(all_notes), "users": len(users.all()),
                 "subjects": len({n["subject"].lower() for n in all_notes})}
        return render_template("index.html", recent=recent, stats=stats)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if g.user:
            return redirect(url_for("notes_list"))
        form = {}
        if request.method == "POST":
            form = {k: request.form.get(k, "").strip() for k in ("username", "email")}
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")
            errors = []
            if not USERNAME_RE.match(form["username"]):
                errors.append("Username must be 3-20 characters: letters, numbers or underscore.")
            if not EMAIL_RE.match(form["email"]) or len(form["email"]) > 120:
                errors.append("Enter a valid email address.")
            if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
                errors.append("Password must be at least 8 characters and include a letter and a number.")
            if password != confirm:
                errors.append("Passwords do not match.")
            if not errors:
                try:
                    create_user(users, form["username"], form["email"], password)
                except ValueError as exc:
                    errors.append(str(exc))
            if errors:
                for e in errors:
                    flash(e, "error")
            else:
                flash("Account created. You can log in now.", "success")
                return redirect(url_for("login"))
        return render_template("register.html", form=form)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("notes_list"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            key = (request.remote_addr, username.lower())
            now = time.time()
            with failed_lock:
                recent = [t for t in failed_logins.get(key, [])
                          if now - t < app.config["LOGIN_WINDOW_SECONDS"]]
                failed_logins[key] = recent
                locked = len(recent) >= app.config["LOGIN_MAX_ATTEMPTS"]
            if locked:
                flash("Too many failed attempts. Try again in a few minutes.", "error")
                return render_template("login.html"), 429
            user = next((u for u in users.all()
                         if u["username"].lower() == username.lower()), None)
            if user and check_password_hash(user["password_hash"], password):
                with failed_lock:
                    failed_logins.pop(key, None)
                session.clear()
                session["user_id"] = user["id"]
                session.permanent = True
                flash("Welcome back, %s!" % user["username"], "success")
                return redirect(safe_next(request.args.get("next"), url_for("notes_list")))
            with failed_lock:
                failed_logins.setdefault(key, []).append(now)
            flash("Incorrect username or password.", "error")
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("index"))

    # ---- notes ------------------------------------------------------------
    @app.route("/notes")
    @login_required
    def notes_list():
        all_notes = notes.all()
        subjects = sorted({n["subject"] for n in all_notes}, key=str.lower)
        results = filter_notes(all_notes, request.args, g.user)
        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        pages = max(1, -(-len(results) // PER_PAGE))
        page = min(page, pages)
        chunk = results[(page - 1) * PER_PAGE: page * PER_PAGE]
        return render_template("notes.html", notes=chunk, total=len(results),
                               page=page, pages=pages, subjects=subjects,
                               f=request.args, back=request.full_path.rstrip("?"))

    @app.route("/upload", methods=["GET", "POST"])
    @login_required
    def upload():
        form = {}
        if request.method == "POST":
            form = {k: request.form.get(k, "").strip() for k in
                    ("title", "subject", "department", "semester", "description")}
            form["subject"] = re.sub(r"\s+", " ", form["subject"])
            errors = []
            if not 3 <= len(form["title"]) <= 100:
                errors.append("Title must be 3-100 characters.")
            if not 2 <= len(form["subject"]) <= 60:
                errors.append("Subject must be 2-60 characters.")
            if form["department"] not in DEPARTMENTS:
                errors.append("Choose a department from the list.")
            semester = None
            if form["semester"]:
                if form["semester"].isdigit() and int(form["semester"]) in SEMESTERS:
                    semester = int(form["semester"])
                else:
                    errors.append("Semester must be between 1 and 8.")
            if len(form["description"]) > 300:
                errors.append("Description can be at most 300 characters.")
            file_info = None
            try:
                file_info = validate_upload(request.files.get("file"))
            except ValueError as exc:
                errors.append(str(exc))
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("upload.html", form=form), 400
            name, ext, data = file_info
            store_note(notes, upload_dir, title=form["title"], description=form["description"],
                       subject=form["subject"], department=form["department"],
                       semester=semester, original_name=name, ext=ext, data=data, user=g.user)
            flash("Note uploaded successfully.", "success")
            return redirect(url_for("notes_list", mine=1))
        return render_template("upload.html", form=form)

    @app.route("/notes/<note_id>/download")
    @login_required
    def download_note(note_id):
        note = get_note_or_404(note_id)

        def bump(data):
            for n in data:
                if n["id"] == note_id:
                    n["downloads"] += 1
        notes.transaction(bump)
        return send_from_directory(upload_dir, note["stored_name"], as_attachment=True,
                                   download_name=note["original_name"])

    @app.route("/notes/<note_id>/view")
    @login_required
    def view_note(note_id):
        note = get_note_or_404(note_id)
        if note["ext"] not in VIEWABLE:
            return redirect(url_for("download_note", note_id=note_id))
        mimetype = "application/pdf" if note["ext"] == "pdf" else "text/plain"
        return send_from_directory(upload_dir, note["stored_name"], mimetype=mimetype,
                                   as_attachment=False, download_name=note["original_name"])

    @app.route("/notes/<note_id>/delete", methods=["POST"])
    @login_required
    def delete_note(note_id):
        note = get_note_or_404(note_id)
        if g.user["role"] != "admin" and note["uploader_id"] != g.user["id"]:
            abort(403)
        remove_notes(notes, upload_dir, lambda n: n["id"] == note_id)
        flash("Deleted \"%s\"." % note["title"], "success")
        return redirect(safe_next(request.form.get("next"), url_for("notes_list")))

    # ---- admin ------------------------------------------------------------
    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        all_notes = notes.all()
        all_users = users.all()
        q = request.args.get("q", "").strip().lower()
        shown = [n for n in all_notes if not q or q in " ".join(
            [n["title"], n["subject"], n["department"], n["uploader_name"]]).lower()]
        shown.sort(key=lambda n: n["uploaded_at"], reverse=True)
        counts = {}
        for n in all_notes:
            counts[n["uploader_id"]] = counts.get(n["uploader_id"], 0) + 1
        stats = {"users": len(all_users), "notes": len(all_notes),
                 "bytes": sum(n["size"] for n in all_notes),
                 "downloads": sum(n["downloads"] for n in all_notes)}
        return render_template("admin.html", notes=shown, users=all_users, counts=counts,
                               stats=stats, q=request.args.get("q", ""),
                               back=request.full_path.rstrip("?"))

    @app.route("/admin/users/<user_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_user(user_id):
        target = next((u for u in users.all() if u["id"] == user_id), None)
        if target is None:
            abort(404)
        if target["role"] == "admin":
            flash("Administrator accounts cannot be deleted here.", "error")
            return redirect(url_for("admin_dashboard"))
        remove_notes(notes, upload_dir, lambda n: n["uploader_id"] == user_id)
        users.transaction(lambda d: d.__setitem__(slice(None), [u for u in d if u["id"] != user_id]))
        flash("User %s and their notes were deleted." % target["username"], "success")
        return redirect(url_for("admin_dashboard"))

    # ---- errors -----------------------------------------------------------
    def error_page(code, title, message):
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(400)
    def e400(_):
        return error_page(400, "Request rejected", "Your form session expired or was invalid. Go back, refresh the page and try again.")

    @app.errorhandler(403)
    def e403(_):
        return error_page(403, "Not allowed", "You do not have permission to do that.")

    @app.errorhandler(404)
    def e404(_):
        return error_page(404, "Not found", "That page or note does not exist.")

    @app.errorhandler(413)
    def e413(_):
        flash("File is too large. The maximum size is %d MB." % MAX_FILE_MB, "error")
        if g.get("user"):
            return redirect(url_for("upload"))
        return error_page(413, "File too large", "The upload exceeded the size limit.")

    @app.errorhandler(500)
    def e500(_):
        return error_page(500, "Something went wrong", "An unexpected error occurred. Please try again.")

    return app


if __name__ == "__main__":
    application = create_app()
    print("NoteShare running at http://127.0.0.1:5000")
    application.run(host="127.0.0.1", port=5000,
                    debug=os.environ.get("FLASK_DEBUG") == "1")
