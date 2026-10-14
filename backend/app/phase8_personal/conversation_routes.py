from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, col, delete, select

from app.core.db import get_session
from app.phase3_rag.rag import HISTORY_TURNS, answer
from app.phase8_personal.courses import require_course
from app.phase8_personal.deps import get_current_user
from app.phase8_personal.models import Conversation, Message, User, utcnow
from app.phase8_personal.profile import weak_points
from app.phase8_personal.schemas import (
    AskInConversation, ConversationCreate, ConversationOut, ConversationUpdate, ExchangeOut, MessageOut,
)

router = APIRouter(prefix="/api/conversations", tags=["Conversations du tuteur"])

DEFAULT_TITLE = "Nouvelle conversation"
AUTO_TITLE_CHARS = 60


def auto_title(question: str) -> str:
    """Titre automatique : les 60 premiers caractères de la première question (sans appel au LLM)."""
    return " ".join(question.split())[:AUTO_TITLE_CHARS].rstrip() or DEFAULT_TITLE


def _out(model, obj):
    return model.model_validate(obj, from_attributes=True)


def get_owned_conversation(conversation_id: int, user: User = Depends(get_current_user),
                           session: Session = Depends(get_session)) -> Conversation:
    """La conversation de l'étudiant, ou 404 (même réponse si elle appartient à un autre étudiant)."""
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation introuvable.")
    return conversation


def _messages(session: Session, conversation_id: int) -> list[Message]:
    return list(session.exec(
        select(Message).where(Message.conversation_id == conversation_id).order_by(col(Message.id))
    ))


@router.get("")
def list_conversations(user: User = Depends(get_current_user),
                       session: Session = Depends(get_session)) -> list[ConversationOut]:
    """Conversations de l'étudiant, la plus récente en premier."""
    rows = session.exec(
        select(Conversation).where(Conversation.user_id == user.id)
        .order_by(col(Conversation.updated_at).desc(), col(Conversation.id).desc())
    )
    return [_out(ConversationOut, c) for c in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_conversation(body: ConversationCreate, user: User = Depends(get_current_user),
                        session: Session = Depends(get_session)) -> ConversationOut:
    if body.course:
        require_course(session, user.id, body.course)
    title = " ".join((body.title or "").split())[:120] or DEFAULT_TITLE
    conversation = Conversation(user_id=user.id, title=title, course=body.course or None)
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return _out(ConversationOut, conversation)


@router.patch("/{conversation_id}")
def rename_conversation(body: ConversationUpdate, conversation: Conversation = Depends(get_owned_conversation),
                        session: Session = Depends(get_session)) -> ConversationOut:
    conversation.title = body.title
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return _out(ConversationOut, conversation)


@router.delete("/{conversation_id}")
def delete_conversation(conversation: Conversation = Depends(get_owned_conversation),
                        session: Session = Depends(get_session)):
    """Supprime la conversation et tous ses messages."""
    session.exec(delete(Message).where(Message.conversation_id == conversation.id))
    session.delete(conversation)
    session.commit()
    return {"deleted": conversation.id}


@router.get("/{conversation_id}/messages")
def list_messages(conversation: Conversation = Depends(get_owned_conversation),
                  session: Session = Depends(get_session)) -> list[MessageOut]:
    return [_out(MessageOut, m) for m in _messages(session, conversation.id)]


@router.post("/{conversation_id}/messages")
def ask_in_conversation(body: AskInConversation, conversation: Conversation = Depends(get_owned_conversation),
                        user: User = Depends(get_current_user),
                        session: Session = Depends(get_session)) -> ExchangeOut:
    """Pose une question dans la conversation : RAG avec les 3 derniers échanges en mémoire, adapté au niveau
    de l'étudiant et à ses points faibles, puis enregistre la question et la réponse (avec ses sources).

    Si le LLM échoue (503), rien n'est enregistré : l'étudiant peut reposer la question.
    """
    if body.course:
        require_course(session, user.id, body.course)

    previous = _messages(session, conversation.id)
    history = [{"role": m.role, "content": m.content} for m in previous[-2 * HISTORY_TURNS:]]
    weak = [p.concept for p in weak_points(session, user.id, body.course or None)]
    result = answer(body.question, body.course, user_id=user.id, history=history, level=user.level,
                    weak_concepts=weak)

    if not previous and conversation.title == DEFAULT_TITLE:
        conversation.title = auto_title(body.question)
    conversation.course = body.course or None
    conversation.updated_at = utcnow()
    question = Message(conversation_id=conversation.id, role="user", content=body.question, course=body.course)
    reply = Message(conversation_id=conversation.id, role="assistant", content=result["answer"],
                    course=body.course, sources=result["sources"], answered=result["answered"])
    session.add_all([conversation, question, reply])
    session.commit()
    for obj in (conversation, question, reply):
        session.refresh(obj)
    return ExchangeOut(conversation=_out(ConversationOut, conversation),
                       user_message=_out(MessageOut, question), assistant_message=_out(MessageOut, reply))
