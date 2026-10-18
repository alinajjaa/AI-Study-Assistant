"""Server-Sent Events : réponse du LLM transmise au fur et à mesure (tuteur, Study Companion).

Format : « event: <nom> » puis « data: <JSON> », séparés par une ligne vide. Un commentaire « : keepalive »
est envoyé toutes les KEEPALIVE_S secondes sans événement (proxys, nginx). Événements :
- token  {"text": "..."}       : fragment de la réponse (non validé, affiché tel quel) ;
- final  {...}                 : résultat complet et validé (réponse, sources…), à afficher à la place du texte ;
- error  {"detail", "status"}  : échec (503 si le LLM est indisponible), même message que les routes classiques.
"""
import json
import logging
import queue
import threading
from collections.abc import Callable, Iterator

from fastapi.responses import StreamingResponse

from app.phase1_llm.llm import LLMError

logger = logging.getLogger("uvicorn.error")

KEEPALIVE_S = 15
HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}  # nginx : pas de mise en tampon


def sse_event(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def error_payload(error: Exception) -> dict:
    if isinstance(error, LLMError):
        return {"detail": str(error), "status": 503}
    if isinstance(error, LookupError):
        return {"detail": str(error), "status": 404}
    logger.exception("Flux SSE : erreur inattendue", exc_info=error)
    return {"detail": "Erreur interne. Réessaie.", "status": 500}


def drain(events: "queue.Queue[tuple[str, object]]") -> Iterator[str]:
    """Événements de la file jusqu'à ("done", None) ; keepalive pendant les silences."""
    while True:
        try:
            kind, data = events.get(timeout=KEEPALIVE_S)
        except queue.Empty:
            yield ": keepalive\n\n"
            continue
        if kind == "done":
            return
        yield sse_event(kind, data)


def stream_work(work: Callable[[Callable[[str], None]], dict]) -> StreamingResponse:
    """Exécute work(on_token) dans un thread et diffuse ses fragments, puis le résultat final (ou l'erreur)."""
    events: queue.Queue = queue.Queue()
    outcome: dict = {}

    def run() -> None:
        try:
            outcome["final"] = work(lambda text: events.put(("token", {"text": text})))
        except Exception as e:  # noqa: BLE001 — transmis au client dans l'événement « error »
            outcome["error"] = e
        finally:
            events.put(("done", None))

    threading.Thread(target=run, daemon=True, name="sse").start()

    def body() -> Iterator[str]:
        yield from drain(events)
        if "error" in outcome:
            yield sse_event("error", error_payload(outcome["error"]))
        else:
            yield sse_event("final", outcome["final"])

    return StreamingResponse(body(), media_type="text/event-stream", headers=HEADERS)
