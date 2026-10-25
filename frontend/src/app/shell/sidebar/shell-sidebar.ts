import { Component, ElementRef, Injector, afterNextRender, inject, input, signal, viewChild } from '@angular/core';
import { Router } from '@angular/router';
import { toMessage } from '../../core/interceptors/error.interceptor';
import { ConversationsService } from '../../core/services/conversations.service';
import { ShellService } from '../../core/services/shell.service';
import { ConversationList } from '../../features/companion/components/conversation-list/conversation-list';
import { Icon } from '../../shared/components/icon/icon';
import { ToastService } from '../../shared/components/toast/toast.service';
import { AccountMenu } from '../account-menu/account-menu';

/**
 * Contenu de la barre latérale (toutes les pages) : nouvelle conversation, recherche, « Récents » (seule zone
 * qui défile) et compte en bas. Repliée en rail : nouvelle conversation, recherche et avatar.
 */
@Component({
  selector: 'app-shell-sidebar',
  imports: [ConversationList, AccountMenu, Icon],
  templateUrl: './shell-sidebar.html',
  styleUrl: './shell-sidebar.css',
})
export class ShellSidebar {
  protected readonly conversations = inject(ConversationsService);
  private readonly shell = inject(ShellService);
  private readonly router = inject(Router);
  private readonly toasts = inject(ToastService);
  private readonly injector = inject(Injector);
  private readonly searchInput = viewChild.required<ElementRef<HTMLInputElement>>('searchInput');

  /** Barre repliée en rail (le menu du compte s'ouvre alors à droite). */
  readonly collapsed = input(false);

  /** Recherche dans les titres des conversations. */
  protected readonly query = signal('');
  protected readonly loadError = signal<string | null>(null);

  constructor() {
    this.load();
  }

  protected load(): void {
    this.loadError.set(null);
    this.conversations.load().subscribe({
      error: (err: unknown) => this.loadError.set(`Conversations indisponibles : ${toMessage(err)}`),
    });
  }

  protected newConversation(): void {
    this.conversations.startNew();
    this.shell.closeMenu();
    this.shell.requestComposerFocus();
    void this.router.navigateByUrl('/companion');
  }

  protected selectConversation(id: number): void {
    this.shell.closeMenu();
    if (id !== this.conversations.activeId()) {
      this.conversations.select(id);
    }
    void this.router.navigateByUrl('/companion');
  }

  protected renameConversation(event: { id: number; title: string }): void {
    this.conversations.rename(event.id, event.title).subscribe({
      error: (err: unknown) => this.toasts.show('error', 'Renommage impossible', toMessage(err)),
    });
  }

  protected removeConversation(id: number): void {
    this.conversations.remove(id).subscribe({
      next: () => this.toasts.show('success', 'Conversation supprimée'),
      error: (err: unknown) => this.toasts.show('error', 'Suppression impossible', toMessage(err)),
    });
  }

  /** Rail « Rechercher » : déplie la barre et place le focus dans la recherche. */
  protected openSearch(): void {
    this.shell.expand();
    afterNextRender(() => this.searchInput().nativeElement.focus(), { injector: this.injector });
  }

  protected onQueryInput(event: Event): void {
    this.query.set((event.target as HTMLInputElement).value);
  }

  /** Échap vide la recherche (sans fermer le tiroir) ; champ déjà vide : comportement habituel. */
  protected onQueryEscape(event: Event): void {
    if (this.query() !== '') {
      event.stopPropagation();
      this.query.set('');
    }
  }
}
