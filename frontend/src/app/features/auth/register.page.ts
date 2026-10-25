import { Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { toMessage } from '../../core/interceptors/error.interceptor';
import { LEVELS, Level, PASSWORD_MAX, PASSWORD_MIN } from '../../core/models/auth.models';
import { AuthService } from '../../core/services/auth.service';
import { Icon } from '../../shared/components/icon/icon';
import { AuthFeatures } from './auth-features';
import { AuthIntro } from './auth-intro';
import { handleRadioKeydown } from '../../shared/utils/radio-group';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Message d'erreur du formulaire d'inscription, ou null s'il est valide. */
export function validateRegistration(email: string, password: string): string | null {
  if (!EMAIL_PATTERN.test(email.trim())) {
    return 'Adresse email invalide.';
  }
  if (password.length < PASSWORD_MIN) {
    return `Le mot de passe doit contenir au moins ${PASSWORD_MIN} caractères.`;
  }
  if (new TextEncoder().encode(password).length > PASSWORD_MAX) {
    return `Le mot de passe ne doit pas dépasser ${PASSWORD_MAX} caractères.`;
  }
  return null;
}

@Component({
  selector: 'app-register-page',
  imports: [RouterLink, AuthIntro, AuthFeatures, Icon],
  templateUrl: './register.page.html',
  styleUrl: './auth.page.css',
})
export class RegisterPage {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly levels = LEVELS;
  protected readonly levelValues = LEVELS.map((l) => l.value);
  protected readonly passwordMin = PASSWORD_MIN;
  protected readonly passwordMax = PASSWORD_MAX;

  protected readonly email = signal('');
  protected readonly password = signal('');
  protected readonly level = signal<Level>('intermediaire');
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly levelDescription = computed(
    () => LEVELS.find((l) => l.value === this.level())?.description ?? '',
  );

  protected readonly setLevel = (value: Level): void => this.level.set(value);
  protected readonly onRadioKeydown = handleRadioKeydown;

  protected onInput(field: 'email' | 'password', event: Event): void {
    (field === 'email' ? this.email : this.password).set((event.target as HTMLInputElement).value);
  }

  protected submit(event: Event): void {
    event.preventDefault();
    if (this.loading()) {
      return;
    }
    const invalid = validateRegistration(this.email(), this.password());
    this.error.set(invalid);
    if (invalid) {
      return;
    }
    this.loading.set(true);
    this.auth
      .register(this.email().trim(), this.password(), this.level())
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: () => void this.router.navigateByUrl('/companion'),
        error: (err: unknown) => this.error.set(toMessage(err)),
      });
  }
}
