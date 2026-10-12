import { Component, inject } from '@angular/core';
import { ToastService } from './toast.service';

/** Pile de notifications, à placer une seule fois dans le shell de l'application. */
@Component({
  selector: 'app-toasts',
  templateUrl: './toast.html',
  styleUrl: './toast.css',
})
export class Toasts {
  protected readonly service = inject(ToastService);
}
