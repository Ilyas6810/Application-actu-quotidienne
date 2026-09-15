// Dates au format AAAA-MM-JJ, à l'heure du téléphone (UTC+4, comme l'édition).

const JOURS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
  "novembre", "décembre"];

const deux = (n: number) => String(n).padStart(2, "0");

export function versTexte(d: Date): string {
  return `${d.getFullYear()}-${deux(d.getMonth() + 1)}-${deux(d.getDate())}`;
}

export function aujourdhui(): string {
  return versTexte(new Date());
}

export function versDate(texte: string): Date {
  const [annee, mois, jour] = texte.split("-").map(Number);
  return new Date(annee, mois - 1, jour);
}

export function decaler(texte: string, jours: number): string {
  const d = versDate(texte);
  d.setDate(d.getDate() + jours);
  return versTexte(d);
}

export function dateLongue(texte: string): string {
  const d = versDate(texte);
  return `${JOURS[d.getDay()]} ${d.getDate()} ${MOIS[d.getMonth()]} ${d.getFullYear()}`;
}

export function dateCourte(texte: string): string {
  const d = versDate(texte);
  return `${d.getDate()} ${MOIS[d.getMonth()].slice(0, 4)}.`;
}

export function nomMois(annee: number, mois: number): string {
  return `${MOIS[mois]} ${annee}`;
}

export function majuscule(texte: string): string {
  return texte.charAt(0).toUpperCase() + texte.slice(1);
}
