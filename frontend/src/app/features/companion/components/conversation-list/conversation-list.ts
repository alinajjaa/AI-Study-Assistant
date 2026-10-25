import { Component, ElementRef, Injector, afterNextRender, computed, inject, input, output, signal, viewChild } from '@angular/core';
import { Conversation } from '../../../../core/models/conversation.models';
import { ConfirmService } from '../../../../shared/components/confirm-dialog/confirm.service';
import { Loader } from '../../../../shared/components/loader/loader';
import { RowMenu, RowMenuItem } from '../row-menu/row-menu';
import { matches } from '../sidebar.utils';

const MENU_ITEMS: RowMenuItem[] = [
  { id: 'rename', label: 'Renommer' },
  { id: 'delete', label: 'Supprimer', danger: true },
];

/** « Récents » de la barre latérale : conversations (la plus récente en tête), sélection, renommer, supprimer. */
@Component({
  selector: 'app-conversation-list',
  imports: [Loader, RowMenu],
  templateUrl: './conversation-list.html',
  styleUrl: './conversation-list.css',
})
export class ConversationList {
  private readonly injector = inject(Injector);
  private readonly confirm = inject(ConfirmService);
  private readonly renameInput = viewChild<ElementRef<HTMLInputElement>>('renameInput');

  readonly conversations = input.required<Conversation[]>();
  /** Conversation ouverte (null = nouvelle conversation). */
  readonly activeId = input<number | null>(null);
  readonly loading = input(false);
  /** Recherche de la barre latérale (titre, sans accents ni casse). */
  readonly query = input('');

  readonly selectConversation = output<number>();
  readonly newConversation = output<void>();
  readonly rename = output<{ id: number; title: string }>();
  readonly remove = output<number>();

  protected readonly menuItems = MENU_ITEMS;
  /** Conversation en cours de renommage. */
  protected readonly editingId = signal<number | null>(null);

  protected readonly filtered = computed(() => this.conversations().filter((c) => matches(c.title, this.query())));

  protected onMenu(action: string, conversation: Conversation): void {
    if (action === 'rename') {
      this.startRename(conversation);
    } else if (action === 'delete') {
      this.onDelete(conversation);
    }
  }

  protected startRename(conversation: Conversation): void {
    this.editingId.set(conversation.id);
    afterNextRender(
      () => {
        const el = this.renameInput()?.nativeElement;
        el?.focus();
        el?.select();
      },
      { injector: this.injector },
    );
  }

  protected onRenameKeydown(event: KeyboardEvent, conversation: Conversation): void {
    if (event.key === 'Enter') {
      event.preventDefault();
      this.commitRename(conversation, (event.target as HTMLInputElement).value);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      // Annule le renommage sans fermer le tiroir qui contient la liste
      event.stopPropagation();
      this.editingId.set(null);
    }
  }

  protected commitRename(conversation: Conversation, value: string): void {
    if (this.editingId() !== conversation.id) {
      return;
    }
    this.editingId.set(null);
    const title = value.trim();
    if (title && title !== conversation.title) {
      this.rename.emit({ id: conversation.id, title });
    }
  }

  protected onDelete(conversation: Conversation): void {
    this.confirm
      .ask({
        title: `Supprimer la conversation « ${conversation.title} » ?`,
        message: 'Tous ses messages seront définitivement effacés.',
        confirmLabel: 'Supprimer',
        danger: true,
      })
      .subscribe((ok) => {
        if (ok) {
          this.remove.emit(conversation.id);
        }
      });
  }
}
