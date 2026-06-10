"""RAG chat: semantic search over past entries, answer with the active AI."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import ai, embeddings
from ..templating import templates

router = APIRouter()


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "chat.html", {"active": "chat", "provider": ai.get_provider(db)}
    )


@router.post("/api/chat", response_class=HTMLResponse)
async def chat(request: Request, question: str = Form(...), db: Session = Depends(get_db)):
    try:
        hits = await embeddings.search(db, question)
        blocks = [embeddings.context_block(e) for e, score in hits if score > 0.3]
        answer = await ai.chat_with_context(db, question, blocks)
        sources = [e for e, score in hits if score > 0.3]
        error = None
    except Exception as exc:
        answer, sources, error = "", [], str(exc)
    return templates.TemplateResponse(
        request,
        "partials/chat_message.html",
        {"question": question, "answer": answer, "sources": sources, "error": error},
    )
