import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { finalize } from 'rxjs';
import { toMessage } from '../../core/interceptors/error.interceptor';
import { QUICK_ACTIONS, QuickAction } from '../../core/models/companion.models';
import { ExamOptions } from '../../core/models/exam.models';
import { UploadResponse } from '../../core/models/tutor.models';
import { CompanionService } from '../../core/services/companion.service';
import { ConversationsService } from '../../core/services/conversations.service';
import { ExamJobsService } from '../../core/services/exam-jobs.service';
import { FlashcardJobsService } from '../../core/services/flashcard-jobs.service';
import { SummaryJobsService } from '../../core/services/summary-jobs.service';
import { TutorApiService } from '../../core/services/tutor-api.service';
import { CourseSelector } from '../../shared/components/course-selector/course-selector';
import { Loader } from '../../shared/components/loader/loader';
import { CompanionThread } from './components/companion-thread/companion-thread';
import { ConversationList } from './components/conversation-list/conversation-list';
import { ExamDialog } from './components/exam-dialog/exam-dialog';
import { QuestionInput } from './components/question-input/question-input';
import { UploadPanel } from './components/upload-panel/upload-panel';

/**
 * Assistant : la page unique après connexion. Conversations, cours (import, examen, suppression) et une seule
 * zone de discussion avec l'agent, qui choisit l'outil (réponse sourcée, résumé, quiz, flashcards, progrès).
 */
@Component({
  selector: 'app-companion-page',
  imports: [ConversationList, CourseSelector, UploadPanel, QuestionInput, CompanionThread, ExamDialog, Loader],
  templateUrl: './companion.page.html',
  styleUrl: './companion.page.css',
})
export class CompanionPage {
  private readonly api = inject(TutorApiService);
  protected readonly companion = inject(CompanionService);
  protected readonly conversations = inject(ConversationsService);
  protected readonly examJobs = inject(ExamJobsService);
  private readonly flashcardJobs = inject(FlashcardJobsService);
  private readonly summaryJobs = inject(SummaryJobsService);
  private readonly questionInput = viewChild.required(QuestionInput);

  protected readonly quickActions = QUICK_ACTIONS;
  protected readonly courses = signal<string[]>([]);
  protected readonly coursesLoading = signal(false);
  protected readonly deleting = signal(false);
  /**
   * Cours sélectionné (null = tous les cours) : seule source de vérité pour la liste « Mes cours », le
   * sélecteur au-dessus de la discussion et le cours envoyé à l'agent.
   */
  protected readonly selectedCourse = signal<string | null>(null);
  protected readonly draft = signal('');
  protected readonly error = signal<string | null>(null);
  /** Cours pour lequel la modale d'examen est ouverte (null = fermée). */
  protected readonly examCourse = signal<string | null>(null);
  protected readonly asking = computed(() => this.conversations.asking());

  /** Générations en arrière-plan par cours (examen, flashcards, résumé) : badge et chronomètre de la liste. */
  private readonly backgroundJobs = computed(() => {
    const byCourse = new Map<string, { startedAt: number; kinds: string[] }>();
    const add = (course: string, startedAt: number, kind: string) => {
      const job = byCourse.get(course);
      if (job === undefined) {
        byCourse.set(course, { startedAt, kinds: [kind] });
      } else if (!job.kinds.includes(kind)) {
        job.startedAt = Math.min(job.startedAt, startedAt);
        job.kinds.push(kind);
      }
    };
    for (const [course, startedAt] of this.examJobs.jobs()) {
      add(course, startedAt, 'Examen');
    }
    for (const [course, startedAt] of this.flashcardJobs.jobs()) {
      add(course, startedAt, 'Flashcards');
    }
    for (const [key, startedAt] of this.summaryJobs.jobs()) {
      add(key.slice(key.indexOf(':') + 1), startedAt, 'Résumé');
    }
    return byCourse;
  });
  protected readonly jobStarts = computed(
    () => new Map([...this.backgroundJobs()].map(([course, job]) => [course, job.startedAt])),
  );
  protected readonly jobLabels = computed(
    () => new Map([...this.backgroundJobs()].map(([course, job]) => [course, `${job.kinds.join(' + ')} en cours…`])),
  );
  protected readonly now = computed(() =>
    Math.max(this.examJobs.now(), this.flashcardJobs.now(), this.summaryJobs.now()),
  );

  constructor() {
    this.loadCourses();
    this.conversations.load().subscribe({
      next: () => this.syncCourseWithConversation(),
      error: (err: unknown) => this.error.set(toMessage(err)),
    });
  }

  protected onSelectConversation(id: number): void {
    if (id !== this.conversations.activeId()) {
      this.conversations.select(id);
      this.syncCourseWithConversation();
    }
  }

  protected onNewConversation(): void {
    this.conversations.startNew();
    this.questionInput().focus();
  }

  protected onRenameConversation(event: { id: number; title: string }): void {
    this.conversations.rename(event.id, event.title).subscribe({
      error: (err: unknown) => this.error.set(toMessage(err)),
    });
  }

  protected onDeleteConversation(id: number): void {
    this.conversations.remove(id).subscribe({
      error: (err: unknown) => this.error.set(toMessage(err)),
    });
  }

  protected onSelectCourse(course: string | null): void {
    this.selectedCourse.set(course);
  }

  protected onCourseChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.selectedCourse.set(value === '' ? null : value);
  }

  protected onUploaded(res: UploadResponse): void {
    this.loadCourses(res.course);
  }

  protected onDeleteCourse(course: string): void {
    this.deleting.set(true);
    this.api
      .deleteCourse(course)
      .pipe(finalize(() => this.deleting.set(false)))
      .subscribe({
        next: () => this.loadCourses(),
        error: (err: unknown) => this.error.set(toMessage(err)),
      });
  }

  protected onOpenExam(course: string): void {
    if (!this.examJobs.isGenerating(course)) {
      this.examCourse.set(course);
    }
  }

  /** La modale se ferme aussitôt ; la génération continue en arrière-plan. */
  protected onGenerateExam(options: ExamOptions): void {
    const course = this.examCourse();
    this.examCourse.set(null);
    if (course !== null) {
      this.examJobs.start(course, options);
    }
  }

  protected onExamDialogClosed(): void {
    this.examCourse.set(null);
  }

  protected onQuickAction(action: QuickAction): void {
    this.send(action.message);
  }

  /** L'assistant a demandé quel cours : on le sélectionne et on renvoie la même demande. */
  protected onChooseCourse(event: { course: string; question: string }): void {
    this.selectedCourse.set(event.course);
    this.send(event.question);
  }

  /** La demande part avec le cours sélectionné, affiché aussi dans le message (« Toi · <cours> »). */
  protected send(message: string): void {
    if (this.asking()) {
      return;
    }
    this.companion.send(message, this.selectedCourse()).subscribe({
      error: (err: unknown) => this.error.set(toMessage(err)),
    });
  }

  protected dismissError(): void {
    this.error.set(null);
  }

  private loadCourses(select: string | null = null): void {
    this.coursesLoading.set(true);
    this.api
      .getCourses()
      .pipe(finalize(() => this.coursesLoading.set(false)))
      .subscribe({
        next: (courses) => {
          this.courses.set(courses);
          const selected = select ?? this.selectedCourse();
          if (selected !== null && courses.includes(selected)) {
            this.selectedCourse.set(selected);
          } else {
            // Un seul cours : sélectionné d'office ; sinon tous les cours (l'agent demande lequel si besoin)
            this.selectedCourse.set(courses.length === 1 ? courses[0] : null);
          }
          // Un cours qui vient d'être importé reste sélectionné
          if (select === null) {
            this.syncCourseWithConversation();
          }
        },
        error: (err: unknown) => this.error.set(toMessage(err)),
      });
  }

  /** Une conversation rouverte reprend le cours de sa dernière demande (s'il existe encore). */
  private syncCourseWithConversation(): void {
    const course = this.conversations.active()?.course;
    if (course && this.courses().includes(course)) {
      this.selectedCourse.set(course);
    }
  }
}
