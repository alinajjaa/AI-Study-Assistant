"""Routes du Study Companion : un message à l'agent (réponse directe ou tâche de fond) et résultats de quiz."""
import time

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.core.db import engine, get_session
from app.phase5_evaluation.tracking import agent_run, log_run_async
from app.phase6_agent.graph import run_agent
from app.phase6_agent.jobs import Job, JobError, jobs
from app.phase6_agent.models import QuizResult
from app.phase6_agent.schemas import (
    CompanionExchange, CompanionRequest, JobOut, QuizResultOut, QuizResultRequest,
)
from app.phase6_agent.tools import AgentContext
from app.phase8_personal.conversation_routes import (
    DEFAULT_TITLE, _messages, _out, auto_title, get_owned_conversation,
)
from app.phase8_personal.courses import list_user_courses, require_course
from app.phase8_personal.deps import get_current_user
from app.phase8_personal.models import Conversation, Message, User, utcnow
from app.phase8_personal.schemas import ConversationOut, MessageOut

router = APIRouter(prefix="/api", tags=["Study Companion"])

SYNC_WAIT_S = 20.0  # au-delà, la route répond 202 et le frontend consulte la tâche
HISTORY_MESSAGES = 6


def process_message(job: Job, user_id: int, conversation_id: int, course: str | None, text: str) -> dict:
    """Exécute l'agent puis enregistre la demande et les réponses (rien n'est enregistré si le LLM échoue)."""
    with Session(engine) as session:
        user = session.get(User, user_id)
        conversation = session.get(Conversation, conversation_id)
        if user is None or conversation is None:
            raise JobError("Conversation introuvable.", 404)
        previous = _messages(session, conversation_id)
        history = [{"role": m.role, "content": m.content} for m in previous[-HISTORY_MESSAGES:]]
        ctx = AgentContext(session=session, user=user, courses=list_user_courses(session, user_id),
                           selected_course=course, history=history, message=text,
                           on_tool=lambda tool: setattr(job, "tool", tool))

        start, error, result = time.perf_counter(), None, None
        try:
            result = run_agent(ctx)
        except Exception as e:
            error = e
            raise
        finally:
            log_run_async("agent", *agent_run(
                tools=result.tools if result else ([job.tool] if job.tool else []),
                fallback=result.fallback if result else False, duration_s=time.perf_counter() - start,
                course=course, level=user.level, error=error))

        # La conversation a pu être supprimée pendant la génération
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise JobError("La conversation a été supprimée pendant que l'assistant travaillait.", 404)
        if not previous and conversation.title == DEFAULT_TITLE:
            conversation.title = auto_title(text)
        conversation.course = course
        conversation.updated_at = utcnow()
        question = Message(conversation_id=conversation_id, role="user", content=text, course=course, kind="text")
        replies = [Message(conversation_id=conversation_id, role="assistant", content=r.content, course=course,
                           kind=r.kind, payload=r.payload, sources=r.sources, answered=r.answered)
                   for r in result.replies]
        session.add_all([conversation, question, *replies])
        session.commit()
        for obj in (conversation, question, *replies):
            session.refresh(obj)
        exchange = CompanionExchange(
            conversation=_out(ConversationOut, conversation), user_message=_out(MessageOut, question),
            assistant_messages=[_out(MessageOut, r) for r in replies], tools=result.tools, fallback=result.fallback,
        )
        return exchange.model_dump(mode="json")


def job_out(job: Job) -> JobOut:
    return JobOut(job_id=job.id, status=job.status, tool=job.tool, elapsed_s=job.elapsed_s,
                  exchange=job.result, error=job.error)


@router.post("/companion/messages")
def send_message(body: CompanionRequest, response: Response, user: User = Depends(get_current_user),
                 session: Session = Depends(get_session)) -> JobOut:
    """Envoie un message à l'agent. Réponse directe (200) si elle est prête en 20 s, sinon 202 avec job_id :
    les outils longs (quiz, flashcards, résumé) continuent en tâche de fond (GET /api/companion/jobs/{id}).
    """
    if body.course:
        require_course(session, user.id, body.course)
    if body.conversation_id is None:
        conversation = Conversation(user_id=user.id, course=body.course)
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
    else:
        conversation = get_owned_conversation(body.conversation_id, user, session)

    # Identifiants lus maintenant : la session de la requête sera fermée quand la tâche s'exécutera
    user_id, conversation_id = user.id, conversation.id
    job = jobs.submit(user_id, lambda j: process_message(j, user_id, conversation_id, body.course, body.message))
    if not job.wait(SYNC_WAIT_S):
        response.status_code = status.HTTP_202_ACCEPTED
    elif job.status == "error":  # échec immédiat (LLM injoignable…) : même code que les autres routes
        raise HTTPException(job.error_status or 500, job.error)
    return job_out(job)


@router.get("/companion/jobs/{job_id}")
def read_job(job_id: str, user: User = Depends(get_current_user)) -> JobOut:
    job = jobs.get(job_id, user.id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tâche introuvable (terminée depuis plus d'une heure ?).")
    return job_out(job)


@router.post("/quiz-results", status_code=status.HTTP_201_CREATED)
def save_quiz_results(body: QuizResultRequest, user: User = Depends(get_current_user),
                      session: Session = Depends(get_session)) -> QuizResultOut:
    """Corrige le quiz (réponses attendues enregistrées dans le message), enregistre un QuizResult par question
    (points faibles du profil) et le score dans le message, pour le réafficher à la réouverture.
    """
    message = session.get(Message, body.message_id)
    conversation = session.get(Conversation, message.conversation_id) if message else None
    if message is None or conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz introuvable.")
    payload = message.payload or {}
    questions = payload.get("questions", [])
    if message.kind != "quiz" or not questions:
        raise HTTPException(422, "Ce message n'est pas un quiz.")
    if payload.get("result"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce quiz a déjà été corrigé.")
    if len(body.answers) != len(questions):
        raise HTTPException(422, f"Réponds aux {len(questions)} questions du quiz.")

    correct = [answer == q["answer"] for answer, q in zip(body.answers, questions)]
    course = payload.get("course") or message.course or ""
    session.add_all([
        QuizResult(user_id=user.id, message_id=message.id, course=course, concept=q.get("concept") or q["question"][:80],
                   question=q["question"], correct=ok)
        for q, ok in zip(questions, correct)
    ])
    # Nouvel objet : SQLAlchemy ne détecte pas une modification en place d'une colonne JSON
    message.payload = {**payload, "result": {"answers": body.answers, "correct": correct, "score": sum(correct),
                                             "total": len(questions), "submitted_at": utcnow().isoformat()}}
    session.add(message)
    session.commit()
    session.refresh(message)
    return QuizResultOut(score=sum(correct), total=len(questions), correct=correct, message=_out(MessageOut, message))
