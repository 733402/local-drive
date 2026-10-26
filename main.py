
import os
import secrets
import mimetypes
from pathlib import Path
from functools import wraps
from flask import (
    Flask, request, Response, redirect, url_for,
    send_file, abort, render_template_string
)
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

app = Flask(__name__)

PASSWORD = os.environ.get("SDDRIVE_PASSWORD", "Iloveanimegirls!73")
USERNAME = "admin"

# Change this if your microSD card uses a different path
STORAGE = Path(os.environ.get(
    "SDDRIVE_ROOT",
    str(Path.home() / "storage" / "external-1" / "SDDrive")
)).resolve()

STORAGE.mkdir(parents=True, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024

def safe_path(relative=""):
    relative = str(relative).replace("\\", "/").strip("/")
    parts = relative.split("/") if relative else []

    if any(p in (".", "..") for p in parts):
        abort(400)

    path = STORAGE.joinpath(*parts).resolve()

    if path != STORAGE and STORAGE not in path.parents:
        abort(403)

    # Prevent symlinks from escaping the storage directory
    current = STORAGE
    for part in parts:
        current = current / part
        if current.is_symlink():
            abort(403)

    return path

def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.authorization

        if not auth or not (
            secrets.compare_digest(auth.username or "", USERNAME)
            and secrets.compare_digest(auth.password or "", PASSWORD)
        ):
            return Response(
                "Login required",
                401,
                {"WWW-Authenticate": 'Basic realm="SDDrive"'}
            )

        return fn(*args, **kwargs)
    return wrapper

PAGE = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SDDrive</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#10131b;color:#edf0fa;
font-family:system-ui,Arial;padding:20px}
main{max-width:950px;margin:auto}
h1{color:#82aaff}
.panel,.item{background:#1b2030;padding:15px;
border-radius:12px;margin:12px 0}
a{color:#82aaff;text-decoration:none;overflow-wrap:anywhere}
input,button{padding:10px;border-radius:8px;
border:1px solid #39425b;margin:4px;max-width:100%}
input{background:#10131b;color:white}
button{background:#82aaff;color:#10131b;cursor:pointer}
.item{display:flex;gap:12px;align-items:center;
justify-content:space-between;flex-wrap:wrap}
form{display:inline-flex;gap:4px;flex-wrap:wrap}
small{color:#aab2c8}
.progress{height:6px;background:#30384b;border-radius:5px;
overflow:hidden;margin-top:12px}
#bar{height:100%;width:0;background:#82aaff}
</style>
</head>
<body>
<main>
<h1>SDDrive</h1>
<p>Your personal cloud storage</p>

<div class="panel">
<b>Storage:</b> microSD card<br>
<b>Folder:</b> /{{ current }}
<hr>
<form id="upload" enctype="multipart/form-data">
<input type="hidden" name="dir" value="{{ current }}">
<input type="file" name="file" required>
<button>Upload</button>
</form>
<div class="progress"><div id="bar"></div></div>
<p id="status"></p>
<hr>
<form method="post" action="/mkdir">
<input type="hidden" name="dir" value="{{ current }}">
<input name="name" placeholder="New folder name" required>
<button>Create folder</button>
</form>
</div>

{% if current %}
<div class="item">
<a href="/?dir={{ parent|urlencode }}">⬅ Parent folder</a>
</div>
{% endif %}

{% for item in folders %}
<div class="item">
<div>📁 <a href="/?dir={{ item.rel|urlencode }}">{{ item.name }}</a></div>
<form method="post" action="/delete">
<input type="hidden" name="path" value="{{ item.rel }}">
<input type="hidden" name="dir" value="{{ current }}">
<button onclick="return confirm('Delete this folder and all its contents?')">
Delete folder</button>
</form>
</div>
{% endfor %}

{% for item in files %}
<div class="item">
<div>
📄 <a href="/download?path={{ item.rel|urlencode }}">{{ item.name }}</a><br>
<small>{{ item.size }} · {{ item.mime }}</small>
</div>
<form method="post" action="/rename">
<input type="hidden" name="path" value="{{ item.rel }}">
<input type="hidden" name="dir" value="{{ current }}">
<input name="name" placeholder="New filename" required>
<button>Rename</button>
</form>
<form method="post" action="/delete">
<input type="hidden" name="path" value="{{ item.rel }}">
<input type="hidden" name="dir" value="{{ current }}">
<button onclick="return confirm('Delete this file?')">Delete</button>
</form>
</div>
{% endfor %}
</main>
<script>
document.getElementById('upload').addEventListener('submit', function(e) {
  e.preventDefault();
  const data = new FormData(this);
  const xhr = new XMLHttpRequest();
  const bar = document.getElementById('bar');
  const status = document.getElementById('status');
  xhr.open('POST', '/upload');
  xhr.upload.onprogress = function(e) {
    if(e.lengthComputable) {
      bar.style.width = (e.loaded/e.total*100) + '%';
      status.textContent = Math.round(e.loaded/e.total*100) + '% uploaded';
    }
  };
  xhr.onload = function() {
    if(xhr.status >= 200 && xhr.status < 400) {
      status.textContent = 'Upload complete';
      location.reload();
    } else {
      status.textContent = 'Upload failed: ' + xhr.responseText;
    }
  };
  xhr.onerror = function() { status.textContent = 'Connection failed'; };
  xhr.send(data);
});
</script>
</body>
</html>
"""

def format_size(size):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024

@app.errorhandler(RequestEntityTooLarge)
def too_large(e):
    return "Upload exceeds the 2 GB limit.", 413

@app.get("/")
@auth_required
def index():
    current = request.args.get("dir", "")
    directory = safe_path(current)

    if not directory.is_dir():
        abort(404)

    folders, files = [], []

    for p in sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if p.is_symlink():
            continue

        rel = p.relative_to(STORAGE).as_posix()

        if p.is_dir():
            folders.append({"name": p.name, "rel": rel})
        elif p.is_file():
            files.append({
                "name": p.name,
                "rel": rel,
                "size": format_size(p.stat().st_size),
                "mime": mimetypes.guess_type(p.name)[0] or "File"
            })

    parent = Path(current).parent.as_posix()
    if parent == ".":
        parent = ""

    return render_template_string(
        PAGE, current=current, parent=parent,
        folders=folders, files=files
    )

@app.post("/upload")
@auth_required
def upload():
    directory = safe_path(request.form.get("dir", ""))

    if not directory.is_dir():
        abort(404)

    file = request.files.get("file")
    if not file or not file.filename:
        return "Select a file.", 400

    name = secure_filename(file.filename)
    if not name:
        return "Invalid filename.", 400

    destination = safe_path(
        (directory.relative_to(STORAGE) / name).as_posix()
    )

    if destination.exists():
        return "A file with that name already exists.", 409

    file.save(destination)
    return "Uploaded", 200

@app.get("/download")
@auth_required
def download():
    path = safe_path(request.args.get("path", ""))

    if not path.is_file():
        abort(404)

    return send_file(path, as_attachment=True,
                     download_name=path.name)

@app.post("/mkdir")
@auth_required
def mkdir():
    directory = safe_path(request.form.get("dir", ""))
    name = request.form.get("name", "").strip()

    if (not name or name in (".", "..")
        or "/" in name or "\\" in name
        or any(ord(c) < 32 for c in name)):
        return "Invalid folder name.", 400

    destination = safe_path(
        (directory.relative_to(STORAGE) / name).as_posix()
    )
    destination.mkdir(exist_ok=False)
    return redirect(url_for("index", dir=request.form.get("dir", "")))

@app.post("/rename")
@auth_required
def rename():
    path = safe_path(request.form.get("path", ""))
    name = request.form.get("name", "").strip()

    if not path.is_file():
        abort(404)

    if (not name or name in (".", "..")
        or "/" in name or "\\" in name
        or any(ord(c) < 32 for c in name)):
        return "Invalid filename.", 400

    destination = safe_path(
        (path.parent.relative_to(STORAGE) / name).as_posix()
    )

    if destination.exists():
        return "That name already exists.", 409

    path.rename(destination)
    return redirect(url_for("index", dir=request.form.get("dir", "")))

@app.post("/delete")
@auth_required
def delete():
    path = safe_path(request.form.get("path", ""))

    if path == STORAGE:
        abort(403)

    if path.is_symlink():
        abort(403)
    elif path.is_file():
        path.unlink()
    elif path.is_dir():
        import shutil
        shutil.rmtree(path)
    else:
        abort(404)

    return redirect(url_for("index", dir=request.form.get("dir", "")))

if __name__ == "__main__":
    print("SDDrive storage:", STORAGE)
    print("Username: admin")
    print("Password: Iloveanimegirls!73")
    print("Open http://127.0.0.1:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
