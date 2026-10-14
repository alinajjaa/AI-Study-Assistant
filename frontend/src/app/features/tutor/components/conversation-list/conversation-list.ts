import { Component, ElementRef, Injector, afterNextRender, inject, input, output, signal, viewChild } from '@angular/core';
import { Conversation } from '../../../../core/models/conversation.models';
import { Loader } from '../../../../shared/components/loader/loader';

const DATE_FORMAT = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short' });

/** Barre latérale « Conversations » du tuteur : nouvelle, sélection, renommer, supprimer. */
@Component({
  selector: 'app-conversation-list',
  imports: [Loader],
  templateUrl: './conversation-list.html',
  styleUrl: './conversation-list.css',
})
export class ConversationList {
  private readonly injector = inject(Injector);
  private readonly renameInput = viewChild<ElementRef<HTMLInputElement>>('renameInput');

  readonly conversations = input.required<Conversation[]>();
  /** Conversation ouverte (null = nouvelle conversation). */
  readonly activeId = input<number | null>(null);
  readonly loading = input(false);

  readonly selectConversation = output<number>();
  readonly newConversation = output<void>();
  readonly rename = output<{ id: number; title: string }>();
  readonly remove = output<number>();

  /** Conversation en cours de renommage. */
  protected readonly editingId = signal<number | null>(null);

  protected date(conversation: Conversation): string {
    return DATE_FORMAT.format(new Date(conversation.updated_at));
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
    const ok = confirm(
      `Supprimer la conversation « ${conversation.title} » ?\nTous ses messages seront définitivement effacés.`,
    );
    if (ok) {
      this.remove.emit(conversation.id);
    }
  }
}
