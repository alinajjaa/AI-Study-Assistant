import { Component, Injector, afterNextRender, computed, effect, inject, signal, untracked, viewChild } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { finalize } from 'rxjs';
import { toMessage } from '../../core/interceptors/error.interceptor';
import { COMPLETE_EXAM_MINUTES } from '../../core/utils/exam.utils';
import { QUICK_ACTIONS, QuickAction } from '../../core/models/companion.models';
import { ExamOptions } from '../../core/models/exam.models';
import { UploadResponse } from '../../core/models/tutor.models';
import { CompanionService } from '../../core/services/companion.service';
import { ConversationsService } from '../../core/services/conversations.service';
import { ExamJobsService } from '../../core/services/exam-jobs.service';
import { ShellService } from '../../core/services/shell.service';
import { TutorApiService } from '../../core/services/tutor-api.service';
import { ErrorState } from '../../shared/components/error-state/error-state';
import { Icon } from '../../shared/components/icon/icon';
import { Skeleton } from '../../shared/components/skeleton/skeleton';
import { StepProgress } from '../../shared/components/step-progress/step-progress';
import { ToastService } from '../../shared/components/toast/toast.service';
import { CompanionThread } from './components/companion-thread/companion-thread';
import { CoursePicker } from './components/course-picker/course-picker';
import { ExamDialog } from './components/exam-dialog/exam-dialog';
import { QuestionInput } from './components/question-input/question-input';
import { UploadPanel } from './components/upload-panel/upload-panel';

const EXAM_STEPS: readonly string[] = ['Lecture du cours', 'QCM', 'Vrai / Faux', 'Questions rédigées', 'Mise en page du PDF'];

/**
 * Assistant : une seule zone de discussion avec l'agent, qui choisit l'outil (réponse sourcée, résumé, quiz,
 * flashcards, progrès). Nouvelle conversation : accueil centré. Le cours se choisit dans la zone de saisie
 * (sélecteur, « + » ou glisser-déposer pour importer un PDF) ; les conversations sont dans la barre latérale.
 */
@Component({
  selector: 'app-companion-page',
  imports: [UploadPanel, QuestionInput, CompanionThread, CoursePicker, ExamDialog, ErrorState, Skeleton, StepProgress, Icon],
  templateUrl: './companion.page.html',
  styleUrl: './companion.page.css',
})
export class CompanionPage {
  private readonly api = inject(TutorApiService);
  protected readonly companion = inject(CompanionService);
  protected readonly conversations = inject(ConversationsService);
  protected readonly examJobs = inject(ExamJobsService);
  private readonly toasts = inject(ToastService);
  private readonly shell = inject(ShellService);
  private readonly injector = inject(Injector);
  private readonly questionInput = viewChild.required(QuestionInput);
  private readonly coursePicker = viewChild(CoursePicker);

  protected readonly quickActions = QUICK_ACTIONS;
  protected readonly courses = signal<string[]>([]);
  protected readonly coursesLoading = signal(false);
  /**
   * Cours sélectionné (null = tous les cours) : seule source de vérité pour le sélecteur de la zone de saisie
   * et le cours envoyé à l'agent.
   */
  protected readonly selectedCourse = signal<string | null>(null);
  protected readonly draft = signal('');
  protected readonly error = signal<string | null>(null);
  /** Action à relancer par « Réessayer » (null : l'erreur n'est pas rejouable, le message se ferme seulement). */
  private readonly retryAction = signal<(() => void) | null>(null);
  protected readonly canRetry = computed(() => this.retryAction() !== null);
  /** « Examen » sans cours choisi : invite à en choisir un. */
  protected readonly courseHint = signal<string | null>(null);
  /** Étapes habituelles d'un examen complet et durée mesurée (indicateur de progression). */
  protected readonly examSteps = EXAM_STEPS;
  protected readonly examEstimateS = COMPLETE_EXAM_MINUTES * 60;
  protected readonly runningExams = computed(() => [...this.examJobs.jobs()].map(([course, startedAt]) => ({ course, startedAt })));
  /** Cours pour lequel la modale d'examen est ouverte (null = fermée). */
  protected readonly examCourse = signal<string | null>(null);
  protected readonly asking = computed(() => this.conversations.asking());
  /** Accueil : conversation sans message (titre, saisie et actions au centre). */
  protected readonly home = computed(
    () => this.conversations.messages().length === 0 && !this.conversations.loadingMessages(),
  );

  constructor() {
    // « Discuter » depuis « Mes cours » : /companion?course=…
    this.loadCourses(inject(ActivatedRoute).snapshot.queryParamMap.get('course'));
    // Conversation ouverte depuis la barre latérale : elle reprend le cours de sa dernière demande
    effect(() => {
      this.conversations.activeId();
      untracked(() => this.syncCourseWithConversation());
    });
    // « Nouvelle conversation » (barre latérale) : focus dans la saisie
    effect(() => {
      if (this.shell.composerFocusRequest()) {
        this.shell.composerFocusRequest.set(false);
        afterNextRender(() => this.questionInput().focus(), { injector: this.injector });
      }
    });
  }

  /** Affiche l'erreur (message déjà traduit en français) ; « Réessayer » relance retry s'il est fourni. */
  private fail(err: unknown, retry: (() => void) | null = null): void {
    this.error.set(toMessage(err));
    this.retryAction.set(retry);
  }

  protected retryFailed(): void {
    const retry = this.retryAction();
    this.dismissError();
    retry?.();
  }

  protected onSelectCourse(course: string | null): void {
    this.selectedCourse.set(course);
    this.courseHint.set(null);
  }

  protected onUploaded(res: UploadResponse): void {
    this.loadCourses(res.course);
  }

  /** « Renvoyer la demande » sous une réponse en erreur : même question, même cours. */
  protected onRetryMessage(event: { question: string; course: string | null }): void {
    this.selectedCourse.set(event.course !== null && this.courses().includes(event.course) ? event.course : null);
    this.send(event.question);
  }

  protected onOpenExam(course: string): void {
    if (this.examJobs.isGenerating(course)) {
      this.toasts.show('info', 'Examen déjà en préparation', `Le PDF de « ${course} » se téléchargera tout seul.`);
    } else {
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

  /** Flashcards, Résumé, Quiz : demande à l'agent sur le cours sélectionné ; Examen : modale d'examen. */
  protected onQuickAction(action: QuickAction): void {
    if (action.message !== null) {
      this.send(action.message);
      return;
    }
    const course = this.selectedCourse();
    if (course === null) {
      this.courseHint.set('Choisis un cours pour générer un examen.');
      this.coursePicker()?.openMenu();
    } else {
      this.onOpenExam(course);
    }
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
      error: (err: unknown) => this.fail(err),
    });
  }

  protected dismissError(): void {
    this.error.set(null);
    this.retryAction.set(null);
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
          // Un cours qui vient d'être importé (ou choisi dans « Mes cours ») reste sélectionné
          if (select === null) {
            this.syncCourseWithConversation();
          }
        },
        error: (err: unknown) => this.fail(err, () => this.loadCourses(select)),
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
