# Project Report: NoteShare, Online Notes Management and Sharing System

## 1. Abstract

College students often share lecture notes through chat groups where files are lost, duplicated, or impossible to search. NoteShare is a web application that gives a department one organised place to upload, find, and download study material. It is built with Python Flask, HTML, CSS and JavaScript. It uses **no database server**: documents are stored in a local `uploads/` folder and all records are stored in JSON files. The system supports registration and login, validated uploads (PDF, Word, PowerPoint, text, Markdown), organisation by department, subject and semester, keyword search with filters, protected downloads, permission-based deletion, and an administrator dashboard. Uploaded files are shielded from direct web access, and every upload is checked for extension, size, file name and real content.

## 2. Objectives

1. Provide a single, searchable repository of class notes.
2. Let students register and log in securely.
3. Accept only safe, supported document types within a size limit.
4. Organise notes by department, subject and semester.
5. Allow search, filtering and sorting so notes are found quickly.
6. Restrict deletion to the uploader and administrators.
7. Give administrators tools to moderate uploaded material and users.
8. Work on laptops and phones.
9. Run on a student PC with only Python installed, with no external database.

## 3. Modules

| Module | Responsibility | Where |
|--------|----------------|-------|
| Authentication | Registration, login, logout, session handling, password hashing, login throttling | `register`, `login`, `logout` in `app.py` |
| Upload and validation | Field checks, extension whitelist, size limit, signature check, file name sanitising, saving under a random name | `validate_upload`, `content_matches`, `store_note` |
| Metadata storage | Thread-safe, atomic JSON read/write | `JsonStore` |
| Browse, search, filter | Keyword search, department/subject/semester/type filters, sort, pagination | `filter_notes`, `notes_list` |
| Download and view | Login-protected file delivery, download counter, inline view for PDF and text | `download_note`, `view_note` |
| Authorisation and deletion | Owner-or-admin check, removes record and file | `delete_note`, `remove_notes` |
| Admin dashboard | Statistics, all-material table, delete notes and users | `admin_dashboard`, `admin_delete_user` |
| Presentation | Jinja2 templates, responsive CSS, client-side checks | `templates/`, `static/` |
| Security layer | CSRF tokens, security headers, safe redirects, error pages | `before_request`, `after_request` hooks |

## 4. System Architecture

**Style:** a three-layer monolith, where the browser talks to Flask, and Flask talks to the local file system.

```
 Browser (HTML, CSS, JavaScript)
        |  HTTP (forms, GET/POST)
        v
 Flask application (app.py)
   - Routes and controllers
   - Validation and permission checks
   - Jinja2 templates
        |
        v
 Local storage
   data/users.json    user records (hashed passwords)
   data/notes.json    note metadata
   uploads/           documents stored as <uuid>.<ext>
```

**Data model**

*User:* `id, username, email, password_hash, role (student|admin), created_at`

*Note:* `id, title, description, subject, department, semester, original_name, stored_name, ext, size, downloads, uploader_id, uploader_name, uploaded_at`

**Upload flow:** form submitted, then CSRF check, login check, field validation, extension whitelist, size check, content signature check, file saved as `uuid.ext`, metadata appended to `notes.json`, success message. If saving the metadata fails, the saved file is removed.

**Download flow:** login check, note looked up by id in `notes.json`, file served from `uploads/` using the stored random name. The user never supplies a path.

**Concurrency:** each JSON store has a lock, and writes go to a temporary file followed by an atomic replace, so a crash cannot leave half-written data.

**Security design**

| Threat | Control |
|--------|---------|
| Direct access to files | `uploads/` is outside `static/`; only login-protected routes serve it |
| Path traversal in file names | `secure_filename`, random stored names, ids looked up rather than paths accepted |
| Malicious or disguised uploads | Extension whitelist plus magic-byte check; `nosniff` header |
| Oversized uploads | Request limit, server check, and client check (10 MB) |
| Weak or leaked passwords | Salted hashes, password rules, lockout after 5 failures in 5 minutes |
| Cross-site request forgery | CSRF token on every POST; SameSite cookies |
| Cross-site scripting | Jinja2 auto-escaping; CSP forbids inline scripts |
| Privilege escalation | Server-side owner/admin checks on delete; admin-only routes return 403 |
| Open redirects | Only local paths accepted for `next` |

## 5. Technologies

Python 3.10+, Flask 3, Werkzeug (password hashing and file name sanitising), Jinja2, HTML5, CSS3 (Grid and Flexbox, media queries), vanilla JavaScript, JSON files, `unittest`.

## 6. Testing

**Approach:** automated tests use Flask's test client with a temporary data folder, so they never touch real data. A manual checklist covers the visual and responsive behaviour.

| Area | Cases | Examples |
|------|-------|----------|
| Authentication | 9 | duplicate user, weak password, wrong password, lockout, CSRF, open redirect |
| Upload validation | 9 | `.exe` rejected, fake PDF rejected, empty and oversize rejected, traversal name neutralised |
| Access control | 8 | direct URL to uploads returns 404, anonymous download redirected, non-owner delete returns 403 |
| Admin | 5 | dashboard, delete any note, delete user with notes, admin protected |
| Search and filter | 6 | keyword, department, subject, type, mine, no results |

Result: **36 automated tests pass** (`python -m unittest discover -s tests -v`). The full case table is in `TEST_CASES.md`.

## 7. Advantages

- Runs anywhere Python runs, with a single dependency (Flask) and no database installation.
- Easy to back up: copy the `data/` and `uploads/` folders.
- Safer than a shared folder: files are not publicly reachable, uploads are validated, and deletion is permission-controlled.
- Fast search and filtering with a clean interface that works on phones.
- Small, readable code base suited to learning and extension.

## 8. Limitations

- JSON storage rewrites the whole file on each change, so it suits hundreds or low thousands of notes, not very large deployments.
- It is designed for a single server process; running several worker processes would need file locking across processes or a real database.
- Search is a simple substring match with no ranking and no search inside document text.
- No email verification or password reset; an admin must handle forgotten passwords.
- Signature checks cannot detect malware inside a valid-looking document; an antivirus scan should be added for public deployment.
- No built-in HTTPS. Use a reverse proxy with TLS before exposing it to the internet.
- Notes are visible to every logged-in user; there are no private or per-class groups.

## 9. Future Enhancements

Password reset by email, note ratings and comments, per-class private groups, full-text search inside PDFs, virus scanning, migrating storage to SQLite or PostgreSQL if usage grows, and cloud object storage for files.

## 10. Conclusion

NoteShare meets its goal of a complete, working notes-sharing platform with only local file storage. Registration, validated uploads, organised browsing, search, protected downloads, permission-based deletion and an admin dashboard are all implemented and tested. The design keeps files private, checks every input on the server, and remains simple enough to install on a student laptop in a few minutes. The listed limitations mainly concern scale, and the modular code makes it straightforward to move to a database later.
