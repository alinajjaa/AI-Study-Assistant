import { Injectable, signal } from '@angular/core';
import { Observable, of } from 'rxjs';

export interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  /** Action destructive (suppression) : bouton rouge. */
  danger?: boolean;
}

export interface ConfirmRequest extends ConfirmOptions {
  resolve: (ok: boolean) => void;
}

/**
 * Confirmation avant une action irréversible, dans une boîte de dialogue au style de l'application
 * (<app-confirm-dialog />, placée une fois dans le shell). Sans boîte montée (composant testé seul),
 * repli sur window.confirm, synchrone.
 */
@Injectable({ providedIn: 'root' })
export class ConfirmService {
  private readonly _request = signal<ConfirmRequest | null>(null);
  private hosts = 0;

  readonly request = this._request.asReadonly();

  attach(): void {
    this.hosts++;
  }

  detach(): void {
    this.hosts = Math.max(0, this.hosts - 1);
  }

  /** Émet true (confirmé) ou false (annulé), une seule fois. */
  ask(options: ConfirmOptions): Observable<boolean> {
    if (this.hosts === 0) {
      return of(window.confirm(`${options.title}\n${options.message}`));
    }
    return new Observable<boolean>((subscriber) => {
      let done = false;
      const request: ConfirmRequest = {
        ...options,
        resolve: (ok) => {
          done = true;
          subscriber.next(ok);
          subscriber.complete();
        },
      };
      this._request()?.resolve(false); // une seule question à la fois
      this._request.set(request);
      return () => {
        if (!done && this._request() === request) {
          this._request.set(null);
        }
      };
    });
  }

  answer(ok: boolean): void {
    const request = this._request();
    this._request.set(null);
    request?.resolve(ok);
  }
}
