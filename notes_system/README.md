# NoteShare: Online Notes Management and Sharing System

A web app where college students register, upload lecture notes (PDF, Word, PowerPoint, text, Markdown), organise them by **department** and **subject**, search and filter, and download. Admins manage all uploaded materials.

Built with **Python Flask, HTML, CSS and JavaScript**. There is **no database server**: documents live in the `uploads/` folder and metadata lives in JSON files in `data/`.

## Quick start on Windows

### 1. Install Python
1. Download Python 3.10 or newer from <https://www.python.org/downloads/>.
2. In the installer, **tick "Add python.exe to PATH"**, then click Install.
3. Check it worked. Open **Command Prompt** and run: `python --version`

### 2. Unzip the project
Right-click `notes_system.zip`, choose **Extract All**, for example to `C:\Projects\notes_system`.

### 3a. Easiest: double-click `run_windows.bat`
It creates a virtual environment, installs the dependencies and starts the server.

### 3b. Or run the commands yourself
Open Command Prompt in the project folder (type `cmd` in the folder's address bar in File Explorer):

```bat
cd C:\Projects\notes_system
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

PowerShell users: if `activate` is blocked, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, then `venv\Scripts\Activate.ps1`.

### 4. Open the app
Go to **http://127.0.0.1:5000** in your browser. Press `Ctrl+C` in the terminal to stop.

## Logins

| Role | Username | Password |
|------|----------|----------|
| Admin (created on first run) | `admin` | `Admin@12345` |
| Student | register on the **Create account** page | your choice |

**Change the admin password before real use.** Set your own before the first run:

```bat
set ADMIN_USERNAME=principal
set ADMIN_PASSWORD=MyStr0ngPassw0rd
python app.py
```
(The admin is only created when no admin exists yet, so set these before the first start. To reset, stop the app, delete `data\users.json` contents back to `[]`, and start again.)

## Load sample notes (optional)
With the virtual environment active:

```bat
python seed_samples.py
```
This adds two demo students (`student1`, `student2`, password `Student@123`) and three sample notes from `sample_notes\`.

## Run the tests
```bat
python -m unittest discover -s tests -v
```
36 automated tests cover registration, login, upload validation, permissions, admin, and search. The manual checklist is in `TEST_CASES.md`.

## Features

1. Register and log in (hashed passwords, 8-hour sessions, lockout after 5 failed logins in 5 minutes).
2. Upload `pdf, doc, docx, ppt, pptx, txt, md` up to 10 MB.
3. Organise by department, subject and optional semester.
4. Browse notes as cards with pagination (9 per page).
5. Search by keyword; filter by department, subject, semester, file type, "my notes"; sort by date, title or downloads.
6. Download any note (login required). PDF, text and Markdown can also be viewed in the browser.
7. Delete a note: the uploader or an admin only.
8. Admin dashboard: totals, search and delete any material, delete student accounts (with their notes).
9. File extension, file size, file content (signature) and file name validation.
10. Success and error messages on every action.
11. Responsive layout for laptops, tablets and phones.

## Security notes

- Uploaded files are stored **outside** `static/` under random names (`uuid.ext`) and are only served by login-protected routes. Direct URLs to `uploads/` return 404.
- The original name goes through `secure_filename`, so `../../x.pdf` becomes `x.pdf`. It is never used as a path.
- File content is checked against the extension (for example a `.pdf` must start with `%PDF-`).
- Every POST form carries a CSRF token. Delete and logout are POST only.
- Passwords use Werkzeug's salted hashes. The session secret is generated once and kept in `data\secret.key` (or set the `SECRET_KEY` environment variable).
- Security headers: `nosniff`, `X-Frame-Options`, a Content Security Policy, and `no-store` caching for logged-in pages.
- Redirect targets are restricted to local paths.

## Project layout

```
notes_system/
  app.py               Flask backend (routes, validation, JSON storage)
  seed_samples.py      Optional demo data loader
  requirements.txt     Flask
  run_windows.bat      One-click setup and run
  templates/           HTML (Jinja2) pages
  static/css, js/      Styles and scripts
  data/                users.json, notes.json (created and updated automatically)
  uploads/             Uploaded documents
  sample_notes/        Files used by seed_samples.py
  tests/test_app.py    Automated tests
  TEST_CASES.md        Manual test checklist
  PROJECT_REPORT.md    Academic report
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `'python' is not recognized` | Re-run the Python installer and tick **Add python.exe to PATH**, or try `py` instead of `python`. |
| `Address already in use` | Another program uses port 5000. Edit the last line of `app.py` and change `port=5000` to `5001`. |
| Browser shows "Request rejected" | The page was open too long or cookies are blocked. Refresh the page and retry. |
| Upload says file too large | The limit is 10 MB. Change `MAX_FILE_MB` at the top of `app.py`. |
| Want other devices on Wi-Fi to connect | Change `host="127.0.0.1"` to `host="0.0.0.0"` in `app.py`, allow Python through Windows Firewall, and open `http://<your-pc-ip>:5000`. Only do this on a trusted network. |

## Running for a class or lab (optional)
Flask's built-in server is for development. For a steadier server on Windows:

```bat
pip install waitress
waitress-serve --host=127.0.0.1 --port=5000 --call app:create_app
```

## Backing up
Copy the `data\` and `uploads\` folders. That is the whole database.
