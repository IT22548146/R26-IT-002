"""
services/upload_service.py
Shared file-upload helper. Stores files under <project_root>/uploads/<subdir>/
and returns a forward-slash relative path for persisting in the DB.
"""

import os
from datetime import datetime
from werkzeug.utils import secure_filename

# <project_root> = the garment_new directory (parent of services/).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def save_upload(file, subdir: str, allowed_exts, max_bytes: int, owner_id="anon") -> str:
    """
    Persist an uploaded file and return its relative path
    (e.g. 'uploads/profile_pics/17_2026....png'), or None if no file given.
    Raises ValueError on a bad extension or an oversized file.

    `allowed_exts` is an iterable of lowercase extensions incl. dot, e.g. {'.png', '.jpg'}.
    """
    if not file or not getattr(file, "filename", ""):
        return None

    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed_exts:
        allowed = ", ".join(sorted(allowed_exts))
        raise ValueError(f"File type '{ext or 'unknown'}' not allowed. Allowed: {allowed}")

    # Size check without trusting the client-provided Content-Length.
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > max_bytes:
        raise ValueError(f"File too large (max {max_bytes // (1024 * 1024)} MB).")

    dest_dir = os.path.join(_PROJECT_ROOT, "uploads", subdir)
    os.makedirs(dest_dir, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    stored_name = f"{owner_id}_{stamp}_{filename}"
    file.save(os.path.join(dest_dir, stored_name))

    return f"uploads/{subdir}/{stored_name}".replace("\\", "/")


def resolve_upload_path(rel_path: str) -> str:
    """
    Resolve a stored relative path to an absolute path, guarding against
    traversal outside the uploads directory. Returns None if invalid/missing.
    """
    if not rel_path:
        return None
    uploads_root = os.path.join(_PROJECT_ROOT, "uploads")
    abs_path = os.path.abspath(os.path.join(_PROJECT_ROOT, rel_path))
    if os.path.commonpath([abs_path, uploads_root]) != uploads_root:
        return None
    if not os.path.isfile(abs_path):
        return None
    return abs_path
