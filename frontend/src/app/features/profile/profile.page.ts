import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { toMessage } from '../../core/interceptors/error.interceptor';
import { LEVELS, Level, levelLabel } from '../../core/models/auth.models';
import { Profile, WeakPoint, formatPercent } from '../../core/models/profile.models';
import { AuthService } from '../../core/services/auth.service';
import { ProfileApiService } from '../../core/services/profile-api.service';
import { Loader } from '../../shared/components/loader/loader';
import { ToastService } from '../../shared/components/toast/toast.service';
import { handleRadioKeydown } from '../../shared/utils/radio-group';

const DISMISSED_KEY = 'ai-study-assistant.level-suggestion-dismissed';

function readDismissed(): string | null {
  try {
    return localStorage.getItem(DISMISSED_KEY);
  } catch {
    return null;
  }
}

function writeDismissed(value: string): void {
  try {
    localStorage.setItem(DISMISSED_KEY, value);
  } catch {
    // Stockage indisponible : la suggestion ignorée réapparaîtra au prochain chargement.
  }
}

/** « Mon profil » : niveau, statistiques, points faibles et suggestion de niveau. */
@Component({
  selector: 'app-profile-page',
  imports: [Loader, RouterLink],
  templateUrl: './profile.page.html',
  styleUrl: './profile.page.css',
})
export class ProfilePage {
  private readonly api = inject(ProfileApiService);
  private readonly auth = inject(AuthService);
  private readonly toasts = inject(ToastService);

  protected readonly levels = LEVELS;
  protected readonly levelValues = LEVELS.map((l) => l.value);
  protected readonly levelLabel = levelLabel;
  protected readonly percent = formatPercent;

  protected readonly profile = signal<Profile | null>(null);
  protected readonly loading = signal(false);
  protected readonly savingLevel = signal(false);
  protected readonly error = signal<string | null>(null);
  private readonly dismissed = signal<string | null>(readDismissed());

  protected readonly level = computed<Level | null>(() => this.profile()?.level ?? null);
  protected readonly levelDescription = computed(
    () => LEVELS.find((l) => l.value === this.level())?.description ?? '',
  );
  /** Suggestion affichée, sauf si l'étudiant l'a ignorée. */
  protected readonly suggestion = computed(() => {
    const profile = this.profile();
    const suggestion = profile?.level_suggestion;
    return suggestion && this.dismissed() !== this.suggestionKey(profile, suggestion.level) ? suggestion : null;
  });

  protected readonly selectLevel = (value: Level): void => this.changeLevel(value);
  protected readonly onRadioKeydown = handleRadioKeydown;

  constructor() {
    this.load();
  }

  protected acceptSuggestion(): void {
    const suggestion = this.suggestion();
    if (suggestion) {
      this.changeLevel(suggestion.level, true);
    }
  }

  protected dismissSuggestion(): void {
    const profile = this.profile();
    const suggestion = profile?.level_suggestion;
    if (profile && suggestion) {
      const key = this.suggestionKey(profile, suggestion.level);
      writeDismissed(key);
      this.dismissed.set(key);
    }
  }

  protected weakLabel(point: WeakPoint): string {
    return `${formatPercent(point.to_review_rate)} à revoir · ${point.reviews} révisions`;
  }

  private changeLevel(level: Level, fromSuggestion = false): void {
    if (level === this.level() || this.savingLevel()) {
      return;
    }
    this.savingLevel.set(true);
    this.auth
      .updateLevel(level)
      .pipe(finalize(() => this.savingLevel.set(false)))
      .subscribe({
        next: () => {
          this.toasts.show(
            'success',
            `Niveau : ${levelLabel(level)}`,
            fromSuggestion ? 'Suggestion acceptée : le tuteur adapte ses explications.' : 'Le tuteur adapte ses explications.',
          );
          this.load();
        },
        error: (err: unknown) => this.toasts.show('error', 'Niveau non modifié', toMessage(err)),
      });
  }

  private load(): void {
    this.loading.set(true);
    this.api
      .getProfile()
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (profile) => {
          this.profile.set(profile);
          this.error.set(null);
        },
        error: (err: unknown) => this.error.set(toMessage(err)),
      });
  }

  /** Une suggestion ignorée ne revient pas, tant qu'elle propose le même niveau au même étudiant. */
  private suggestionKey(profile: Profile, level: Level): string {
    return `${this.auth.user()?.id ?? ''}:${profile.level}->${level}`;
  }
}
