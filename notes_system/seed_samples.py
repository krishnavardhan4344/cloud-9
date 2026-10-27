"""Load demo users and the files in ./sample_notes into the system.

Run once (optional):   python seed_samples.py
Demo logins: student1 / Student@123   and   student2 / Student@123
"""
from pathlib import Path

from app import create_app, create_user, store_note, validate_upload

SAMPLES = [
    ("Data_Structures_Unit1_Arrays_and_Linked_Lists.txt", "Arrays and Linked Lists (Unit 1)",
     "Data Structures", "Computer Science", 3, "Complexity table and practice questions.", "student1"),
    ("Thermodynamics_Laws_Summary.md", "Laws of Thermodynamics: Summary",
     "Thermodynamics", "Mechanical Engineering", 4, "Zeroth to third law with a worked check.", "student2"),
    ("Engineering_Mathematics_Matrices_Cheatsheet.pdf", "Matrices Cheat Sheet",
     "Engineering Mathematics", "Mathematics", 2, "Rank, determinant, eigenvalues in one page.", "student1"),
]


class _Upload:
    """Minimal stand-in for a werkzeug FileStorage so validate_upload can be reused."""
    def __init__(self, path):
        self.filename, self._fh = path.name, open(path, "rb")

    def read(self, n=-1):
        return self._fh.read(n)


def main():
    app = create_app()
    folder = Path(__file__).parent / "sample_notes"
    users = {}
    for name, email in (("student1", "student1@example.com"), ("student2", "student2@example.com")):
        try:
            users[name] = create_user(app.users, name, email, "Student@123")
        except ValueError:
            users[name] = next(u for u in app.users.all() if u["username"] == name)
    existing = {n["title"] for n in app.notes.all()}
    for fname, title, subject, dept, sem, desc, owner in SAMPLES:
        if title in existing:
            continue
        display, ext, data = validate_upload(_Upload(folder / fname))
        store_note(app.notes, app.upload_dir, title=title, description=desc, subject=subject,
                   department=dept, semester=sem, original_name=display, ext=ext, data=data,
                   user=users[owner])
        print("Added:", title)
    print("Done. Log in as student1 / Student@123")


if __name__ == "__main__":
    main()
