import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from .tools import check_connection

router = APIRouter()

UPLOAD_DIR = "/app/data/uploads/email"
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB

@router.get("/status")
async def get_email_status(connection_id: str = ""):
    """Return the API status for the dashboard."""
    if not connection_id:
        return {"status": "error", "message": "No connection ID provided"}
    return await check_connection(connection_id)


@router.post("/upload")
async def upload_attachment(file: UploadFile = File(...)):
    """Upload a file that can be used as an email attachment."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = os.path.splitext(file.filename)[1]
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content)} bytes). Maximum: {MAX_UPLOAD_SIZE} bytes (25 MB)."
        )

    with open(file_path, "wb") as f:
        f.write(content)

    return {
        "status": "ok",
        "file_path": file_path,
        "original_name": file.filename,
        "size": len(content),
    }
