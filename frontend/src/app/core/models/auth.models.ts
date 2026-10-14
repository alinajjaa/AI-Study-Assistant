export type Level = 'debutant' | 'intermediaire' | 'avance';

export const LEVELS: readonly { value: Level; label: string; description: string }[] = [
  { value: 'debutant', label: 'Débutant', description: 'Mots simples, définitions et exemples concrets' },
  { value: 'intermediaire', label: 'Intermédiaire', description: 'Termes du cours expliqués avec un exemple' },
  { value: 'avance', label: 'Avancé', description: 'Réponses précises et techniques' },
];

export function levelLabel(level: Level): string {
  return LEVELS.find((l) => l.value === level)?.label ?? level;
}

export interface User {
  id: number;
  email: string;
  level: Level;
  created_at: string;
}

/** Réponse de POST /api/auth/login et /api/auth/register. */
export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

/** Bornes du mot de passe (bcrypt ignore au-delà de 72 octets). */
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 72;
