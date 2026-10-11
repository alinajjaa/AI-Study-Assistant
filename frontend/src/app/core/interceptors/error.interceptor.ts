import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';

const UNREACHABLE = 'Backend injoignable : vérifie que uvicorn tourne sur le port 8000';
const GENERIC = 'Une erreur inattendue est survenue';

/** Extrait le champ "detail" renvoyé par FastAPI, s'il est lisible. */
function readDetail(body: unknown): string | null {
  if (typeof body !== 'object' || body === null || !('detail' in body)) {
    return null;
  }
  const detail = body.detail;
  if (typeof detail === 'string') {
    return detail;
  }
  // Erreurs de validation Pydantic : [{ msg: string, ... }]
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item: unknown) =>
        typeof item === 'object' && item !== null && 'msg' in item && typeof item.msg === 'string'
          ? item.msg
          : null,
      )
      .filter((msg): msg is string => msg !== null);
    return messages.length ? messages.join(' ; ') : null;
  }
  return null;
}

/** Transforme toute HttpErrorResponse en Error portant un message lisible en français. */
export const errorInterceptor: HttpInterceptorFn = (req, next) =>
  next(req).pipe(
    catchError((err: unknown) => {
      if (!(err instanceof HttpErrorResponse)) {
        return throwError(() => err);
      }
      const message =
        err.status === 0 ? UNREACHABLE : (readDetail(err.error) ?? `${GENERIC} (code ${err.status})`);
      return throwError(() => new Error(message));
    }),
  );

/** Message affichable à partir d'une erreur quelconque. */
export function toMessage(err: unknown): string {
  return err instanceof Error ? err.message : GENERIC;
}
