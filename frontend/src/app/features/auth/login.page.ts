import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { toMessage } from '../../core/interceptors/error.interceptor';
import { AuthService } from '../../core/services/auth.service';

/** Page à rouvrir après connexion : uniquement un chemin interne. */
export function safeReturnUrl(value: string | null): string {
  return value && value.startsWith('/') && !value.startsWith('//') ? value : '/tutor';
}

@Component({
  selector: 'app-login-page',
  imports: [RouterLink],
  templateUrl: './login.page.html',
  styleUrl: './auth.page.css',
})
export class LoginPage {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly email = signal('');
  protected readonly password = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  /** Arrivé ici parce que la session a expiré (ou n'existait pas). */
  protected readonly redirected = this.route.snapshot.queryParamMap.has('returnUrl');

  protected onInput(field: 'email' | 'password', event: Event): void {
    (field === 'email' ? this.email : this.password).set((event.target as HTMLInputElement).value);
  }

  protected submit(event: Event): void {
    event.preventDefault();
    if (this.loading()) {
      return;
    }
    if (!this.email().trim() || !this.password()) {
      this.error.set('Renseigne ton email et ton mot de passe.');
      return;
    }
    this.error.set(null);
    this.loading.set(true);
    this.auth
      .login(this.email().trim(), this.password())
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: () => void this.router.navigateByUrl(safeReturnUrl(this.route.snapshot.queryParamMap.get('returnUrl'))),
        error: (err: unknown) => this.error.set(toMessage(err)),
      });
  }
}
