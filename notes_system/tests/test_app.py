"""Automated test cases. Run from the project folder:  python -m unittest discover -s tests -v"""
import io
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import create_app, MAX_FILE_BYTES  # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def make_docx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
    return buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.app = create_app({"DATA_DIR": root / "data", "UPLOAD_DIR": root / "uploads",
                               "TESTING": True})
        self.upload_dir = root / "uploads"
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def token(self, client, url="/login"):
        html = client.get(url).get_data(as_text=True)
        return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)

    def register(self, client, username="alice", email="alice@example.com", pw="Passw0rdx"):
        return client.post("/register", data={"_csrf": self.token(client, "/register"),
                           "username": username, "email": email, "password": pw, "confirm": pw},
                           follow_redirects=True)

    def login(self, client, username="alice", pw="Passw0rdx"):
        return client.post("/login", data={"_csrf": self.token(client), "username": username,
                           "password": pw}, follow_redirects=True)

    def new_client(self, username, email):
        c = self.app.test_client()
        self.register(c, username, email)
        self.login(c, username)
        return c

    def upload(self, client, name="unit1.pdf", content=PDF, title="Unit 1 notes",
               subject="Thermodynamics", department="Mechanical Engineering", **extra):
        data = {"_csrf": self.token(client, "/upload"), "title": title, "subject": subject,
                "department": department, "semester": "3", "description": "demo",
                "file": (io.BytesIO(content), name)}
        data.update(extra)
        return client.post("/upload", data=data, content_type="multipart/form-data",
                           follow_redirects=True)

    def first_note(self):
        return self.app.notes.all()[0]


class AuthTests(Base):
    def test_register_and_login(self):
        r = self.register(self.client)
        self.assertIn("Account created", r.get_data(as_text=True))
        r = self.login(self.client)
        self.assertIn("Welcome back", r.get_data(as_text=True))

    def test_duplicate_username_rejected(self):
        self.register(self.client)
        r = self.register(self.app.test_client(), email="other@example.com")
        self.assertIn("already taken", r.get_data(as_text=True))

    def test_weak_password_rejected(self):
        r = self.register(self.client, pw="short")
        self.assertIn("at least 8 characters", r.get_data(as_text=True))

    def test_wrong_password(self):
        self.register(self.client)
        r = self.login(self.client, pw="WrongPass1")
        self.assertIn("Incorrect username or password", r.get_data(as_text=True))

    def test_passwords_are_hashed(self):
        self.register(self.client)
        user = [u for u in self.app.users.all() if u["username"] == "alice"][0]
        self.assertNotIn("Passw0rdx", str(user))
        self.assertTrue(user["password_hash"].startswith(("scrypt:", "pbkdf2:")))

    def test_lockout_after_repeated_failures(self):
        self.register(self.client)
        for _ in range(5):
            self.login(self.client, pw="WrongPass1")
        r = self.login(self.client, pw="Passw0rdx")
        self.assertEqual(r.status_code, 429)

    def test_protected_pages_redirect_to_login(self):
        for url in ("/notes", "/upload", "/admin"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302)
            self.assertIn("/login", r.headers["Location"])

    def test_open_redirect_blocked(self):
        self.register(self.client)
        r = self.client.post("/login?next=//evil.com", data={"_csrf": self.token(self.client),
                             "username": "alice", "password": "Passw0rdx"})
        self.assertNotIn("evil.com", r.headers["Location"])

    def test_csrf_required(self):
        r = self.client.post("/login", data={"username": "a", "password": "b"})
        self.assertEqual(r.status_code, 400)


class UploadTests(Base):
    def setUp(self):
        super().setUp()
        self.alice = self.new_client("alice", "alice@example.com")

    def test_valid_pdf_upload(self):
        r = self.upload(self.alice)
        self.assertIn("uploaded successfully", r.get_data(as_text=True))
        note = self.first_note()
        self.assertTrue((self.upload_dir / note["stored_name"]).exists())
        self.assertNotEqual(note["stored_name"], "unit1.pdf")

    def test_valid_docx_upload(self):
        r = self.upload(self.alice, name="slides.docx", content=make_docx())
        self.assertIn("uploaded successfully", r.get_data(as_text=True))

    def test_disallowed_extension(self):
        r = self.upload(self.alice, name="virus.exe", content=b"MZ....")
        self.assertIn("not allowed", r.get_data(as_text=True))
        self.assertEqual(len(self.app.notes.all()), 0)

    def test_fake_pdf_content_rejected(self):
        r = self.upload(self.alice, name="fake.pdf", content=b"<?php echo 1; ?>")
        self.assertIn("does not match", r.get_data(as_text=True))

    def test_empty_file_rejected(self):
        r = self.upload(self.alice, content=b"")
        self.assertIn("empty", r.get_data(as_text=True))

    def test_oversize_file_rejected(self):
        big = PDF + b"0" * (MAX_FILE_BYTES + 10)
        r = self.upload(self.alice, content=big)
        self.assertIn("too large", r.get_data(as_text=True))
        self.assertEqual(len(self.app.notes.all()), 0)

    def test_missing_fields_rejected(self):
        r = self.upload(self.alice, title="x", department="Nonsense")
        text = r.get_data(as_text=True)
        self.assertIn("Title must be", text)
        self.assertIn("Choose a department", text)

    def test_filename_traversal_is_neutralised(self):
        self.upload(self.alice, name="../../etc/passwd.pdf")
        note = self.first_note()
        self.assertNotIn("..", note["original_name"])
        self.assertNotIn("/", note["original_name"])
        self.assertEqual(note["original_name"], "passwd.pdf")
        self.assertEqual(list(self.upload_dir.glob("*"))[0].parent, self.upload_dir)

    def test_markdown_and_text_allowed(self):
        r = self.upload(self.alice, name="notes.md", content=b"# Hello\n")
        self.assertIn("uploaded successfully", r.get_data(as_text=True))


class AccessTests(Base):
    def setUp(self):
        super().setUp()
        self.alice = self.new_client("alice", "alice@example.com")
        self.bob = self.new_client("bob", "bob@example.com")
        self.upload(self.alice)
        self.note = self.first_note()

    def test_uploads_folder_not_web_accessible(self):
        anon = self.app.test_client()
        for url in ("/uploads/" + self.note["stored_name"], "/static/../uploads/" + self.note["stored_name"]):
            self.assertEqual(anon.get(url).status_code, 404)

    def test_download_requires_login(self):
        r = self.app.test_client().get("/notes/%s/download" % self.note["id"])
        self.assertEqual(r.status_code, 302)

    def test_logged_in_download_and_counter(self):
        r = self.bob.get("/notes/%s/download" % self.note["id"])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, PDF)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        self.assertEqual(self.first_note()["downloads"], 1)

    def test_view_pdf_inline(self):
        r = self.bob.get("/notes/%s/view" % self.note["id"])
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertNotIn("attachment", r.headers.get("Content-Disposition", ""))

    def test_unknown_note_404(self):
        self.assertEqual(self.bob.get("/notes/doesnotexist/download").status_code, 404)

    def test_other_student_cannot_delete(self):
        r = self.bob.post("/notes/%s/delete" % self.note["id"],
                          data={"_csrf": self.token(self.bob, "/notes")})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(len(self.app.notes.all()), 1)

    def test_owner_can_delete_and_file_removed(self):
        r = self.alice.post("/notes/%s/delete" % self.note["id"],
                            data={"_csrf": self.token(self.alice, "/notes")}, follow_redirects=True)
        self.assertIn("Deleted", r.get_data(as_text=True))
        self.assertEqual(len(self.app.notes.all()), 0)
        self.assertFalse((self.upload_dir / self.note["stored_name"]).exists())

    def test_student_cannot_open_admin(self):
        self.assertEqual(self.bob.get("/admin").status_code, 403)


class AdminTests(Base):
    def setUp(self):
        super().setUp()
        self.alice = self.new_client("alice", "alice@example.com")
        self.upload(self.alice)
        self.note = self.first_note()
        self.admin = self.app.test_client()
        self.login(self.admin, "admin", "Admin@12345")

    def test_admin_dashboard_lists_materials(self):
        r = self.admin.get("/admin")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Unit 1 notes", r.get_data(as_text=True))

    def test_admin_can_delete_any_note(self):
        self.admin.post("/notes/%s/delete" % self.note["id"],
                        data={"_csrf": self.token(self.admin, "/admin")})
        self.assertEqual(len(self.app.notes.all()), 0)

    def test_admin_can_delete_user_and_their_notes(self):
        uid = [u for u in self.app.users.all() if u["username"] == "alice"][0]["id"]
        self.admin.post("/admin/users/%s/delete" % uid,
                        data={"_csrf": self.token(self.admin, "/admin")})
        self.assertEqual(len(self.app.notes.all()), 0)
        self.assertFalse(any(u["username"] == "alice" for u in self.app.users.all()))

    def test_admin_account_cannot_be_deleted(self):
        uid = [u for u in self.app.users.all() if u["role"] == "admin"][0]["id"]
        self.admin.post("/admin/users/%s/delete" % uid,
                        data={"_csrf": self.token(self.admin, "/admin")})
        self.assertTrue(any(u["role"] == "admin" for u in self.app.users.all()))


class SearchTests(Base):
    def setUp(self):
        super().setUp()
        self.c = self.new_client("alice", "alice@example.com")
        self.upload(self.c, title="Heat engines", subject="Thermodynamics", department="Mechanical Engineering")
        self.upload(self.c, name="a.txt", content=b"hello", title="Graph theory", subject="Discrete Maths", department="Computer Science")
        self.upload(self.c, name="b.md", content=b"# x", title="Sorting", subject="Data Structures", department="Computer Science")

    def count(self, query):
        return self.c.get("/notes?" + query).get_data(as_text=True).count('class="note"')

    def test_keyword_search(self):
        self.assertEqual(self.count("q=heat"), 1)

    def test_department_filter(self):
        self.assertEqual(self.count("department=Computer+Science"), 2)

    def test_subject_filter(self):
        self.assertEqual(self.count("subject=thermodynamics"), 1)

    def test_type_filter(self):
        self.assertEqual(self.count("type=md"), 1)

    def test_no_results(self):
        self.assertIn("Nothing matches", self.c.get("/notes?q=zzzz").get_data(as_text=True))

    def test_mine_filter(self):
        bob = self.new_client("bob", "bob@example.com")
        self.assertEqual(bob.get("/notes?mine=1").get_data(as_text=True).count('class="note"'), 0)
        self.assertEqual(self.count("mine=1"), 3)


if __name__ == "__main__":
    unittest.main()
