import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { errorInterceptor, readBlobDetail } from './error.interceptor';

function jsonBlob(body: unknown): Blob {
  return new Blob([JSON.stringify(body)], { type: 'application/json' });
}

describe('readBlobDetail', () => {
  it('lit le "detail" d\'un Blob JSON', async () => {
    expect(await readBlobDetail(jsonBlob({ detail: 'Cours introuvable' }))).toBe('Cours introuvable');
  });

  it('renvoie null si le Blob n\'est pas du JSON valide', async () => {
    expect(await readBlobDetail(new Blob(['<html>Erreur</html>'], { type: 'text/html' }))).toBeNull();
  });

  it('renvoie null si le JSON n\'a pas de "detail"', async () => {
    expect(await readBlobDetail(jsonBlob({ message: 'x' }))).toBeNull();
  });
});

describe('errorInterceptor', () => {
  let http: HttpClient;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(withInterceptors([errorInterceptor])), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  /** Lance la requête, répond, et renvoie le message de l'erreur produite. */
  async function errorMessage(
    request: Promise<unknown>,
    respond: () => void,
  ): Promise<string> {
    respond();
    try {
      await request;
    } catch (err) {
      return err instanceof Error ? err.message : 'pas une Error';
    }
    return 'aucune erreur';
  }

  it('extrait "detail" d\'un corps d\'erreur Blob (requête responseType blob)', async () => {
    const request = firstValueFrom(http.post('/api/courses/X/exam', {}, { responseType: 'blob' }));
    const message = await errorMessage(request, () =>
      backend
        .expectOne('/api/courses/X/exam')
        .flush(jsonBlob({ detail: 'Cours « X » introuvable' }), { status: 404, statusText: 'Not Found' }),
    );
    expect(message).toBe('Cours « X » introuvable');
  });

  it('se replie sur un message générique si le Blob d\'erreur n\'est pas du JSON', async () => {
    const request = firstValueFrom(http.post('/api/exam', {}, { responseType: 'blob' }));
    const message = await errorMessage(request, () =>
      backend
        .expectOne('/api/exam')
        .flush(new Blob(['Bad Gateway']), { status: 503, statusText: 'Service Unavailable' }),
    );
    expect(message).toBe('Une erreur inattendue est survenue (code 503)');
  });

  it('garde le comportement JSON du tuteur', async () => {
    const request = firstValueFrom(http.post('/api/upload', {}));
    const message = await errorMessage(request, () =>
      backend
        .expectOne('/api/upload')
        .flush({ detail: 'Seuls les fichiers PDF sont acceptés' }, { status: 400, statusText: 'Bad Request' }),
    );
    expect(message).toBe('Seuls les fichiers PDF sont acceptés');
  });

  it('signale un backend injoignable (status 0)', async () => {
    const request = firstValueFrom(http.get('/api/courses'));
    const message = await errorMessage(request, () =>
      backend.expectOne('/api/courses').error(new ProgressEvent('error'), { status: 0 }),
    );
    expect(message).toContain('Backend injoignable');
  });
});
