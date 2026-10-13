"""
Task Studio HTTP layer. Both endpoints stay behind the passcode (not in app._OPEN_ENDPOINTS).

  GET  /api/studio/info  -> {max_upload_mb, max_prompt_chars, models, provider}
  POST /api/studio/run   multipart: prompt (required), title, author, files (1+; folder uploads send
                         relative paths as filenames; exactly one .zip is extracted)
                         -> {title, summary, steps, changes, notes, model, zip_name, zip_b64, pdf_name, pdf_b64, readme_md}
  Errors: 400 bad input, 413 too big, 502 model failed / unusable output.
"""
import os

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from api.domain.studio.pipeline import StudioJob
from api.domain.studio.providers import ProviderError, studio_models
from api.domain.studio.sources import ProjectTooLarge, SourceError

MAX_UPLOAD_MB = 4
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MULTIPART_SLACK = 512 * 1024  # form fields + part headers on top of the file bytes
MAX_PROMPT = 4000
MAX_TITLE = 150
MAX_AUTHOR = 120

studio_bp = Blueprint("studio", __name__, url_prefix="/api/studio")


def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _too_big():
    return _err(f"The upload is larger than {MAX_UPLOAD_MB} MB. Remove large data files, build output or "
                "dependencies (node_modules, venv) and try again.", 413)


@studio_bp.route("/info", methods=["GET"])
def info():
    return jsonify({"status": "success", "data": {
        "max_upload_mb": MAX_UPLOAD_MB, "max_prompt_chars": MAX_PROMPT, "models": studio_models(),
        "provider": (os.getenv("STUDIO_PROVIDER") or "gemini").lower()}})


@studio_bp.route("/run", methods=["POST"])
def run():
    if request.content_length and request.content_length > MAX_UPLOAD_BYTES + MULTIPART_SLACK:
        return _too_big()
    try:
        form, files = request.form, request.files.getlist("files")
    except RequestEntityTooLarge:
        return _err("Too many files in one upload. Zip the project and upload the .zip instead.", 413)

    prompt = (form.get("prompt") or "").strip()
    if not prompt:
        return _err("Describe the task in the prompt.")
    if len(prompt) > MAX_PROMPT:
        return _err(f"The prompt is too long ({len(prompt)} characters; the limit is {MAX_PROMPT}).")

    uploads, total = [], 0
    for f in files:
        data = f.read(MAX_UPLOAD_BYTES - total + 1)
        total += len(data)
        if total > MAX_UPLOAD_BYTES:
            return _too_big()
        uploads.append((f.filename or "", data))
    if not uploads:
        return _err("Upload a project: a .zip, a folder or at least one file.")

    job = StudioJob(uploads, prompt, title=(form.get("title") or "").strip()[:MAX_TITLE] or None,
                    author=(form.get("author") or "").strip()[:MAX_AUTHOR] or None)
    try:
        result = job.run()
    except ProjectTooLarge as e:
        return _err(str(e), 413)
    except SourceError as e:
        return _err(str(e), 400)
    except ProviderError as e:
        return _err(str(e), 502)
    return jsonify({"status": "success", "data": result.to_dict()})
