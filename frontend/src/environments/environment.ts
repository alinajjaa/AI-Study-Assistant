// Build de production (Docker, Hugging Face Spaces) : l'API est servie sur la même origine que le frontend
// (nginx redirige /api vers le backend, ou FastAPI sert les deux). En développement (ng serve), voir
// environment.development.ts.
export const environment = {
  apiUrl: '/api',
};
