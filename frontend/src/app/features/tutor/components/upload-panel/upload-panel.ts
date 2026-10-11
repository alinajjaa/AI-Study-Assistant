import { Component, ElementRef, computed, inject, output, signal, viewChild } from '@angular/core';
import { toMessage } from '../../../../core/interceptors/error.interceptor';
import { UploadResponse } from '../../../../core/models/tutor.models';
import { TutorApiService } from '../../../../core/services/tutor-api.service';

const MAX_SIZE_MB = 50;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

/** Taille lisible en français : « 820 Ko », « 12,4 Mo ». */
function formatSize(bytes: number): string {
  const kb = bytes / 1024;
  if (kb < 1024) {
    return `${Math.max(1, Math.round(kb))} Ko`;
  }
  return `${(kb / 1024).toFixed(1).replace('.', ',')} Mo`;
}

@Component({
  selector: 'app-upload-panel',
  templateUrl: './upload-panel.html',
  styleUrl: './upload-panel.css',
})
export class UploadPanel {
  private readonly api = inject(TutorApiService);
  private readonly fileInput = viewChild.required<ElementRef<HTMLInputElement>>('fileInput');

  /** Émis après une indexation réussie. */
  readonly uploaded = output<UploadResponse>();

  protected readonly maxSizeMb = MAX_SIZE_MB;
  protected readonly file = signal<File | null>(null);
  protected readonly fileSize = computed(() => {
    const file = this.file();
    return file ? formatSize(file.size) : '';
  });
  protected readonly courseName = signal('');
  protected readonly dragging = signal(false);
  protected readonly uploading = signal(false);
  protected readonly success = signal<string | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly canUpload = computed(() => this.file() !== null && !this.uploading());

  protected onFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectFile(input.files?.item(0) ?? null);
  }

  protected onDragOver(event: DragEvent): void {
    event.preventDefault();
    if (!this.uploading()) {
      this.dragging.set(true);
    }
  }

  protected onDragLeave(event: DragEvent): void {
    const zone = event.currentTarget as HTMLElement;
    // Ignore les sorties vers un élément enfant de la zone.
    if (!(event.relatedTarget instanceof Node) || !zone.contains(event.relatedTarget)) {
      this.dragging.set(false);
    }
  }

  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
    if (!this.uploading()) {
      this.selectFile(event.dataTransfer?.files.item(0) ?? null);
    }
  }

  protected onCourseNameInput(event: Event): void {
    this.courseName.set((event.target as HTMLInputElement).value);
  }

  protected clearFile(): void {
    this.file.set(null);
    this.fileInput().nativeElement.value = '';
  }

  protected upload(): void {
    const file = this.file();
    if (!file || this.uploading()) {
      return;
    }
    this.uploading.set(true);
    this.success.set(null);
    this.error.set(null);

    this.api.upload(file, this.courseName()).subscribe({
      next: (res) => {
        this.uploading.set(false);
        this.success.set(`Cours « ${res.course} » indexé (${res.chunks} extraits).`);
        this.courseName.set('');
        this.clearFile();
        this.uploaded.emit(res);
      },
      error: (err: unknown) => {
        this.uploading.set(false);
        this.error.set(toMessage(err));
      },
    });
  }

  private selectFile(file: File | null): void {
    this.success.set(null);
    this.error.set(null);
    if (!file) {
      return;
    }

    const rejection = this.validate(file);
    if (rejection) {
      this.error.set(rejection);
      this.clearFile();
      return;
    }
    this.file.set(file);
  }

  private validate(file: File): string | null {
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    if (!isPdf) {
      return `« ${file.name} » n'est pas un PDF : seuls les fichiers PDF sont acceptés.`;
    }
    if (file.size > MAX_SIZE_BYTES) {
      return `Le fichier fait ${formatSize(file.size)} : la taille maximale est de ${MAX_SIZE_MB} Mo.`;
    }
    return null;
  }
}
