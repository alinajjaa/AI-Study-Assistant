import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth.interceptor';
import { errorInterceptor } from './core/interceptors/error.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // authInterceptor après errorInterceptor : il voit le statut 401 avant sa conversion en Error
    provideHttpClient(withInterceptors([errorInterceptor, authInterceptor])),
    provideRouter(routes),
  ],
};
