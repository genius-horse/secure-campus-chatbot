from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, require_admin
from schemas.knowledge import KnowledgeManageRequest
from services.retrieval_service import get_visible_knowledge
from services import knowledge_service as kb
from services.file_parser import parse_file, extract_title, generate_kb_id, extract_keywords, FileParserError
from models.user import User

router = APIRouter()


@router.get("/knowledge")
def list_visible(
    include_content: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = get_visible_knowledge(db, user.role, include_content=include_content)
    return {"items": items}


@router.post("/knowledge/manage")
def manage(
    payload: KnowledgeManageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    action = payload.action.strip().lower()

    if action == "list":
        docs = kb.list_all(db)
        return {
            "items": [
                {
                    "id": d.id,
                    "title": d.title,
                    "min_role": d.min_role,
                    "sensitivity": d.sensitivity,
                    "keywords": d.keywords,
                    "content": d.content,
                }
                for d in docs
            ]
        }

    if action == "add":
        if not payload.id or not payload.title or not payload.content:
            raise HTTPException(status_code=400, detail="ID、标题和内容为必填项")
        try:
            doc = kb.create(
                db,
                doc_id=payload.id.strip(),
                title=payload.title.strip(),
                min_role=payload.min_role or "public",
                sensitivity=payload.sensitivity or "public",
                keywords=payload.keywords or [],
                content=payload.content.strip(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {"ok": True, "item": {
            "id": doc.id,
            "title": doc.title,
            "min_role": doc.min_role,
            "sensitivity": doc.sensitivity,
            "keywords": doc.keywords,
            "content": doc.content,
        }}

    if action == "update":
        if not payload.id:
            raise HTTPException(status_code=400, detail="缺少id字段")
        updates = {}
        for field in ("title", "min_role", "sensitivity", "content"):
            val = getattr(payload, field)
            if val is not None:
                updates[field] = val.strip() if isinstance(val, str) else val
        if payload.keywords is not None:
            updates["keywords"] = payload.keywords
        try:
            doc = kb.update(db, payload.id.strip(), **updates)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"ok": True, "item": {
            "id": doc.id,
            "title": doc.title,
            "min_role": doc.min_role,
            "sensitivity": doc.sensitivity,
            "keywords": doc.keywords,
            "content": doc.content,
        }}

    if action == "delete":
        if not payload.id:
            raise HTTPException(status_code=400, detail="缺少id字段")
        try:
            kb.delete(db, payload.id.strip())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"ok": True}

    raise HTTPException(status_code=400, detail=f"不支持的操作：{action}")


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名称")

    try:
        content = await file.read()
        text = parse_file(file.filename, content)
    except FileParserError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not text.strip():
        raise HTTPException(status_code=400, detail="文件内容为空或无法解析")

    title = extract_title(text, file.filename)
    doc_id = generate_kb_id(file.filename, title)
    keywords = extract_keywords(text)

    # Check for duplicate ID
    existing = kb.get_by_id(db, doc_id)
    if existing:
        import uuid
        doc_id = f"{doc_id}-{uuid.uuid4().hex[:6]}"

    try:
        doc = kb.create(
            db,
            doc_id=doc_id,
            title=title,
            min_role="public",
            sensitivity="internal",
            keywords=keywords,
            content=text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "ok": True,
        "item": {
            "id": doc.id,
            "title": doc.title,
            "min_role": doc.min_role,
            "sensitivity": doc.sensitivity,
            "keywords": doc.keywords,
            "content_preview": doc.content[:200] + "..." if len(doc.content) > 200 else doc.content,
        },
    }
