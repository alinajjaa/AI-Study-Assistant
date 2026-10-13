import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { finalize } from 'rxjs';
import { toMessage } from '../../core/interceptors/error.interceptor';
import { ExamOptions } from '../../core/models/exam.models';
import { ChatMessage, UploadResponse } from '../../core/models/tutor.models';
import { ExamJobsService } from '../../core/services/exam-jobs.service';
import { TutorApiService } from '../../core/services/tutor-api.service';
import { ChatThread } from './components/chat-thread/chat-thread';
import { CourseSelector } from '../../shared/components/course-selector/course-selector';
import { ExamDialog } from './components/exam-dialog/exam-dialog';
import { QuestionInput } from './components/question-input/question-input';
import { UploadPanel } from './components/upload-panel/upload-panel';

@Component({
  selector: 'app-tutor-page',
  imports: [UploadPanel, CourseSelector, ChatThread, QuestionInput, ExamDialog],
  templateUrl: './tutor.page.html',
  styleUrl: './tutor.page.css',
})
export class TutorPage {
  private readonly api = inject(TutorApiService);
  protected readonly examJobs = inject(ExamJobsService);
  private readonly questionInput = viewChild.required(QuestionInput);
  private nextMessageId = 1;

  protected readonly courses = signal<string[]>([]);
  protected readonly coursesLoading = signal(false);
  /** null = tous les cours. */
  protected readonly selectedCourse = signal<string | null>(null);
  protected readonly deleting = signal(false);
  protected readonly messages = signal<ChatMessage[]>([]);
  protected readonly draft = signal('');
  protected readonly error = signal<string | null>(null);
  /** Cours pour lequel la modale d'examen est ouverte (null = fermée). */
  protected readonly examCourse = signal<string | null>(null);
  protected readonly asking = computed(() => this.messages().some((m) => m.status === 'pending'));

  constructor() {
    this.loadCourses();
  }

  protected onSelectCourse(course: string | null): void {
    this.selectedCourse.set(course);
  }

  protected onUploaded(res: UploadResponse): void {
    this.selectedCourse.set(res.course);
    this.loadCourses();
  }

  protected onSuggestion(text: string): void {
    this.draft.set(text);
    this.questionInput().focus();
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

  protected onDeleteCourse(course: string): void {
    this.deleting.set(true);
    this.api
      .deleteCourse(course)
      .pipe(finalize(() => this.deleting.set(false)))
      .subscribe({
        next: () => {
          if (this.selectedCourse() === course) {
            this.selectedCourse.set(null);
          }
          this.loadCourses();
        },
        error: (err: unknown) => this.error.set(toMessage(err)),
      });
  }

  protected onAsk(question: string): void {
    const id = this.nextMessageId++;
    const course = this.selectedCourse();
    this.messages.update((list) => [
      ...list,
      { id, question, course, status: 'pending', response: null, error: null },
    ]);

    this.api.ask(question, course).subscribe({
      next: (response) => this.updateMessage(id, { status: 'done', response }),
      error: (err: unknown) => {
        const message = toMessage(err);
        this.updateMessage(id, { status: 'error', error: message });
        this.error.set(message);
      },
    });
  }

  protected dismissError(): void {
    this.error.set(null);
  }

  private loadCourses(): void {
    this.coursesLoading.set(true);
    this.api
      .getCourses()
      .pipe(finalize(() => this.coursesLoading.set(false)))
      .subscribe({
        next: (courses) => {
          this.courses.set(courses);
          const selected = this.selectedCourse();
          if (selected !== null && !courses.includes(selected)) {
            this.selectedCourse.set(null);
          }
        },
        error: (err: unknown) => this.error.set(toMessage(err)),
      });
  }

  private updateMessage(id: number, patch: Partial<ChatMessage>): void {
    this.messages.update((list) => list.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  }
}
