# Test Cases

Automated: `python -m unittest discover -s tests -v` (36 tests). Manual steps below can be run in the browser.

| ID | Module | Steps | Expected result | Automated test |
|----|--------|-------|-----------------|----------------|
| TC01 | Register | Fill valid username, email, password; submit | "Account created", redirected to login | test_register_and_login |
| TC02 | Register | Reuse an existing username | Error: username already taken | test_duplicate_username_rejected |
| TC03 | Register | Password `short` | Error: at least 8 characters with letter and number | test_weak_password_rejected |
| TC04 | Login | Wrong password | Error: incorrect username or password | test_wrong_password |
| TC05 | Login | 5 wrong attempts, then correct password | Blocked with "Too many failed attempts" (HTTP 429) | test_lockout_after_repeated_failures |
| TC06 | Security | Open `/notes`, `/upload`, `/admin` while logged out | Redirected to login | test_protected_pages_redirect_to_login |
| TC07 | Security | Login with `?next=//evil.com` | Redirect stays on this site | test_open_redirect_blocked |
| TC08 | Security | POST a form without CSRF token | HTTP 400 | test_csrf_required |
| TC09 | Security | Stored passwords inspected in `users.json` | Only salted hashes | test_passwords_are_hashed |
| TC10 | Upload | Upload a valid PDF | "Note uploaded successfully"; file saved under a random name | test_valid_pdf_upload |
| TC11 | Upload | Upload a valid .docx | Accepted | test_valid_docx_upload |
| TC12 | Upload | Upload `virus.exe` | Error: file type not allowed; nothing stored | test_disallowed_extension |
| TC13 | Upload | Rename a text file to `fake.pdf` and upload | Error: content does not match extension | test_fake_pdf_content_rejected |
| TC14 | Upload | Upload a 0-byte file | Error: file is empty | test_empty_file_rejected |
| TC15 | Upload | Upload a file over 10 MB | Error: file too large; nothing stored | test_oversize_file_rejected |
| TC16 | Upload | Title `x`, department not chosen | Field errors shown, form values kept | test_missing_fields_rejected |
| TC17 | Upload | File named `../../etc/passwd.pdf` | Stored as `passwd.pdf`; saved inside `uploads/` only | test_filename_traversal_is_neutralised |
| TC18 | Upload | Upload `.md` and `.txt` | Accepted | test_markdown_and_text_allowed |
| TC19 | Access | Request the uploaded file by direct URL without login | 404 (folder is not public) | test_uploads_folder_not_web_accessible |
| TC20 | Access | Download while logged out | Redirected to login | test_download_requires_login |
| TC21 | Download | Download while logged in | File content identical; download counter +1 | test_logged_in_download_and_counter |
| TC22 | View | Click View on a PDF | Opens inline in the browser | test_view_pdf_inline |
| TC23 | Delete | Another student POSTs delete | HTTP 403; note remains | test_other_student_cannot_delete |
| TC24 | Delete | Owner deletes own note | Record and file removed; success message | test_owner_can_delete_and_file_removed |
| TC25 | Admin | Student opens `/admin` | HTTP 403 | test_student_cannot_open_admin |
| TC26 | Admin | Admin opens dashboard | All materials listed | test_admin_dashboard_lists_materials |
| TC27 | Admin | Admin deletes any note | Removed | test_admin_can_delete_any_note |
| TC28 | Admin | Admin deletes a student | User and their notes removed | test_admin_can_delete_user_and_their_notes |
| TC29 | Admin | Try to delete the admin account | Refused | test_admin_account_cannot_be_deleted |
| TC30 | Search | Search `heat` | Only matching note shown | test_keyword_search |
| TC31 | Filter | Department = Computer Science | Only that department | test_department_filter |
| TC32 | Filter | Subject, type and "My notes" filters | Correct subsets | test_subject_filter, test_type_filter, test_mine_filter |
| TC33 | Search | Search `zzzz` | "Nothing matches those filters" | test_no_results |

## Manual-only checks

| ID | Check | Expected |
|----|-------|----------|
| M01 | Resize the browser to 375 px wide | Menu collapses to a Menu button; cards stack; admin tables become labelled rows |
| M02 | Choose a `.exe` file in the upload form | Message appears under the file field before submitting |
| M03 | Click Delete | Browser asks for confirmation first |
| M04 | Success message | Fades after about 6 seconds; can be closed with the x button |
| M05 | Restart the server | Users and notes are still there (JSON persistence) |
