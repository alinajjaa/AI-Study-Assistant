import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Observable, catchError, from, switchMap, throwError } from 'rxjs';

const UNREACHABLE = 'Backend injoignable : vérifie que le serveur de l’API est démarré';
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

/**
 * Avec responseType 'blob', le corps d'erreur arrive lui aussi en Blob :
 * on le lit comme texte puis comme JSON. Repli sur null si ce n'est pas du JSON valide.
 */
export async function readBlobDetail(blob: Blob): Promise<string | null> {
  try {
    return readDetail(JSON.parse(await blob.text()));
  } catch {
    return null;
  }
}

function toError(err: HttpErrorResponse, detail: string | null): Error {
  if (err.status === 0) {
    return new Error(UNREACHABLE);
  }
  return new Error(detail ?? `${GENERIC} (code ${err.status})`);
}

/** Transforme toute HttpErrorResponse en Error portant un message lisible en français. */
export const errorInterceptor: HttpInterceptorFn = (req, next) =>
  next(req).pipe(
    catchError((err: unknown): Observable<never> => {
      if (!(err instanceof HttpErrorResponse)) {
        return throwError(() => err);
      }
      if (err.error instanceof Blob) {
        return from(readBlobDetail(err.error)).pipe(
          switchMap((detail) => throwError(() => toError(err, detail))),
        );
      }
      return throwError(() => toError(err, readDetail(err.error)));
    }),
  );

/** Message affichable à partir d'une erreur quelconque. */
export function toMessage(err: unknown): string {
  return err instanceof Error ? err.message : GENERIC;
}
