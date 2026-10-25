import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    CondPageBreak, Flowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from app.phase4_exam.schemas import (
    Exam, ExamSection, MCQQuestion, ShortAnswerQuestion, TrueFalseQuestion,
)

LETTERS = "ABCD"
DIFFICULTY_LABELS = {"facile": "Facile", "moyen": "Moyen", "difficile": "Difficile"}

# Mêmes couleurs que l'interface : bleu nuit pour le texte, vert profond pour l'accent
INK = colors.HexColor("#1b2638")
ACCENT = colors.HexColor("#1f5f4a")
MUTED = colors.HexColor("#5b6472")
LINE = colors.HexColor("#c9cfd6")
ROW_ALT = colors.HexColor("#f4f6f4")
SECTION_BG = colors.HexColor("#eef4f1")

_base = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("title", parent=_base["Title"], fontName="Helvetica-Bold",
                            fontSize=20, textColor=INK, spaceAfter=4),
    "subtitle": ParagraphStyle("subtitle", parent=_base["Normal"], fontSize=10.5,
                               textColor=MUTED, alignment=TA_CENTER, spaceAfter=14),
    "instructions": ParagraphStyle("instructions", parent=_base["Normal"], fontSize=9.5,
                                   textColor=MUTED, spaceBefore=10, spaceAfter=12),
    "section": ParagraphStyle("section", parent=_base["Normal"], fontName="Helvetica-Bold",
                              fontSize=12.5, leading=16, textColor=ACCENT),
    "section_hint": ParagraphStyle("section_hint", parent=_base["Normal"], fontName="Helvetica-Oblique",
                                   fontSize=9.5, leading=12, textColor=MUTED),
    "question": ParagraphStyle("question", parent=_base["Normal"], fontName="Helvetica-Bold",
                               fontSize=11, leading=15, textColor=INK, spaceAfter=5),
    "choice": ParagraphStyle("choice", parent=_base["Normal"], fontSize=10.5, leading=14, textColor=INK),
    "label": ParagraphStyle("label", parent=_base["Normal"], fontSize=9.5, leading=12, textColor=MUTED,
                            spaceBefore=4, spaceAfter=2),
    "h2": ParagraphStyle("h2", parent=_base["Heading2"], textColor=ACCENT, spaceAfter=6),
    "h3": ParagraphStyle("h3", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=11,
                         textColor=ACCENT, spaceBefore=12, spaceAfter=6),
    "cell": ParagraphStyle("cell", parent=_base["Normal"], fontSize=9.5, leading=12.5, textColor=INK),
    "head": ParagraphStyle("head", parent=_base["Normal"], fontName="Helvetica-Bold",
                           fontSize=9.5, leading=12.5, textColor=colors.white),
}

WRITING_LINES = {"vrai_faux": 2, "courte": 4, "ouverte": 14}  # lignes pour écrire la réponse


def fmt_points(points: float) -> str:
    """1 → « 1 pt », 2 → « 2 pts », 1.5 → « 1,5 pt »."""
    text = f"{points:g}".replace(".", ",")
    return f"{text} pt" if points <= 1.5 else f"{text} pts"


# ---------------------------------------------------------------------------
# Petits éléments dessinés (indépendants des polices installées)
# ---------------------------------------------------------------------------

class CheckBox(Flowable):
    """Petite case vide à cocher."""

    def __init__(self, size: float = 9):
        super().__init__()
        self.size = size

    def wrap(self, available_width, available_height):
        return self.size, self.size

    def draw(self):
        self.canv.setStrokeColor(INK)
        self.canv.setLineWidth(0.8)
        self.canv.rect(0, -1, self.size, self.size, stroke=1, fill=0)


class WritingLines(Flowable):
    """Lignes horizontales sur lesquelles l'étudiant écrit sa réponse."""

    def __init__(self, count: int, spacing: float = 20):
        super().__init__()
        self.count = count
        self.spacing = spacing

    def wrap(self, available_width, available_height):
        self.line_width = available_width
        return available_width, self.count * self.spacing

    def draw(self):
        self.canv.setStrokeColor(LINE)
        self.canv.setLineWidth(0.6)
        for i in range(self.count):
            y = (self.count - i - 1) * self.spacing + 2
            self.canv.line(14, y, self.line_width, y)


def _boxes_table(rows: list[list], widths: list[float]) -> Table:
    """Tableau sans bordure : des cases à cocher alignées sur la première ligne du texte."""
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    # Les colonnes paires contiennent les cases, les colonnes impaires le texte
    for col in range(0, len(widths), 2):
        style += [("LEFTPADDING", (col, 0), (col, -1), 12), ("RIGHTPADDING", (col, 0), (col, -1), 4)]
    for col in range(1, len(widths), 2):
        style += [("LEFTPADDING", (col, 0), (col, -1), 2)]
    table.setStyle(TableStyle(style))
    return table


# ---------------------------------------------------------------------------
# En-tête, pied de page et parties du sujet
# ---------------------------------------------------------------------------

def _footer(exam: Exam):
    """Pied de page : nom du cours à gauche, numéro de page à droite."""
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(2 * cm, 1.6 * cm, A4[0] - 2 * cm, 1.6 * cm)
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(2 * cm, 1.2 * cm, f"Examen — {exam.course} · Généré par AI Study Assistant")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def _duration(exam: Exam) -> str:
    """Durée conseillée : 1 h 30 pour l'examen complet, 1 min 30 par question pour un QCM."""
    if exam.format == "complet":
        return "1 h 30"
    return f"{max(10, round(exam.question_count * 1.5))} min"


def _header(exam: Exam) -> list:
    """Titre, informations sur l'examen, cadre pour l'étudiant et consigne générale."""
    total = f"{exam.total_points:g}".replace(".", ",")
    candidate = Table(
        [
            ["Nom : _____________________________", "Prénom : __________________________"],
            ["Classe : ___________________________", f"Note : ________ / {total}"],
        ],
        colWidths=[8.5 * cm, 8.5 * cm],
    )
    candidate.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    if exam.format == "complet":
        rule = "Répondez directement sur ce sujet. Le barème est indiqué pour chaque partie et chaque question."
    else:
        rule = "Pour chaque question, cochez une seule réponse. Le barème est indiqué pour chaque question."
    return [
        Paragraph(f"Examen — {escape(exam.course)}", STYLES["title"]),
        Paragraph(
            f"Difficulté : {DIFFICULTY_LABELS[exam.difficulty]} · Durée conseillée : {_duration(exam)}"
            f" · Noté sur {total} · Généré le {date.today():%d/%m/%Y}",
            STYLES["subtitle"],
        ),
        candidate,
        Paragraph(f"Consigne : {rule}", STYLES["instructions"]),
    ]


def _section_banner(section: ExamSection, show_title: bool) -> list:
    """Bandeau de partie : « Partie A — QCM (8 points) » et sa consigne."""
    if not show_title:
        return []
    total = f"{section.total_points:g}".replace(".", ",")
    banner = Table(
        [[Paragraph(f"Partie {section.letter} — {escape(section.title)} ({total} points)", STYLES["section"])],
         [Paragraph(escape(section.instructions), STYLES["section_hint"])]],
        colWidths=[17 * cm],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SECTION_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
    ]))
    return [CondPageBreak(5 * cm), banner, Spacer(1, 10)]


def _question_title(number: int, text: str, points: float) -> Paragraph:
    return Paragraph(
        f"{number}. {escape(text)} <font name='Helvetica' size='9' color='#5b6472'>({fmt_points(points)})</font>",
        STYLES["question"],
    )


def _render_question(number: int, q, points: float) -> KeepTogether:
    """Une question du sujet, mise en page selon son type."""
    if isinstance(q, MCQQuestion):
        rows = [[CheckBox(), Paragraph(f"<b>{letter}.</b> {escape(choice)}", STYLES["choice"])]
                for letter, choice in zip(LETTERS, q.choices)]
        body = [_question_title(number, q.question, points), _boxes_table(rows, [0.9 * cm, 15.6 * cm])]
    elif isinstance(q, TrueFalseQuestion):
        body = [
            _question_title(number, q.statement, points),
            _boxes_table([[CheckBox(), Paragraph("Vrai", STYLES["choice"]),
                           CheckBox(), Paragraph("Faux", STYLES["choice"])]],
                         [0.9 * cm, 2 * cm, 0.9 * cm, 2 * cm]),
            Paragraph("Justification :", STYLES["label"]),
            WritingLines(WRITING_LINES["vrai_faux"]),
        ]
    elif isinstance(q, ShortAnswerQuestion):
        body = [_question_title(number, q.question, points), WritingLines(WRITING_LINES["courte"])]
    else:  # OpenQuestion
        body = [_question_title(number, q.question, points), WritingLines(WRITING_LINES["ouverte"])]
    return KeepTogether(body + [Spacer(1, 12)])  # une question n'est jamais coupée entre deux pages


def _questions(exam: Exam) -> list:
    """Toutes les parties du sujet, avec une numérotation continue des questions."""
    story, number = [], 1
    show_titles = exam.format == "complet"
    for section in exam.sections:
        story += _section_banner(section, show_titles)
        for q in section.questions:
            story.append(_render_question(number, q, section.points_per_question))
            number += 1
    return story


# ---------------------------------------------------------------------------
# Corrigé
# ---------------------------------------------------------------------------

def _key_table(headers: list[str], rows: list[list], widths: list[float]) -> Table:
    data = [[Paragraph(h, STYLES["head"]) for h in headers]]
    data += [[Paragraph(str(cell), STYLES["cell"]) for cell in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _section_key(section: ExamSection, first_number: int) -> Table:
    """Tableau du corrigé pour une partie, selon le type de ses questions."""
    numbers = range(first_number, first_number + len(section.questions))
    pts = fmt_points(section.points_per_question)
    first = section.questions[0]

    if isinstance(first, MCQQuestion):
        rows = [[n, f"<b>{q.answer}</b>", escape(q.explanation), f"p.{q.page}"]
                for n, q in zip(numbers, section.questions)]
        return _key_table(["N°", "Réponse", "Explication", "Page"], rows,
                          [1.1 * cm, 2.2 * cm, 11.7 * cm, 2 * cm])
    if isinstance(first, TrueFalseQuestion):
        rows = [[n, f"<b>{'Vrai' if q.answer else 'Faux'}</b>", escape(q.correction), f"p.{q.page}"]
                for n, q in zip(numbers, section.questions)]
        return _key_table(["N°", "Réponse", f"Justification attendue ({pts} : réponse et justification)", "Page"],
                          rows, [1.1 * cm, 2.2 * cm, 11.7 * cm, 2 * cm])
    if isinstance(first, ShortAnswerQuestion):
        rows = [[n, escape(q.expected_answer), f"p.{q.page}"] for n, q in zip(numbers, section.questions)]
        return _key_table(["N°", f"Réponse attendue ({pts})", "Page"], rows, [1.1 * cm, 13.9 * cm, 2 * cm])
    # Questions de réflexion : les 4 éléments attendus se partagent les points de la question
    share = fmt_points(section.points_per_question / 4)
    rows = [[n, "<br/>".join(f"• {escape(p)} ({share})" for p in q.expected_points), f"p.{q.page}"]
            for n, q in zip(numbers, section.questions)]
    return _key_table(["N°", "Éléments de réponse attendus", "Page"], rows, [1.1 * cm, 13.9 * cm, 2 * cm])


def _answer_key(exam: Exam) -> list:
    """Corrigé complet : un tableau par partie, avec le barème."""
    summary = " · ".join(f"Partie {s.letter} : {s.total_points:g} pts" for s in exam.sections)
    story = [
        Paragraph("Corrigé et barème", STYLES["h2"]),
        Paragraph("Réservé à l'enseignant. Le corrigé est généré par IA : relisez-le avant de noter. "
                  "Chaque réponse renvoie à la page du cours concernée.", STYLES["instructions"]),
        Paragraph(f"<b>Barème :</b> {summary} — <b>Total : {exam.total_points:g} points</b>",
                  STYLES["instructions"]),
    ]
    number = 1
    for section in exam.sections:
        total = f"{section.total_points:g}".replace(".", ",")
        if exam.format == "complet":
            story.append(Paragraph(f"Partie {section.letter} — {escape(section.title)} ({total} points)",
                                   STYLES["h3"]))
        story.append(_section_key(section, number))
        number += len(section.questions)
    return story


def render_exam_pdf(exam: Exam, include_answers: bool = True) -> bytes:
    """Met en page l'examen en PDF et renvoie le fichier sous forme d'octets."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2.2 * cm,
        title=f"Examen - {exam.course}", author="AI Study Assistant",
    )
    story = _header(exam) + _questions(exam)
    if include_answers:
        story += [PageBreak()] + _answer_key(exam)  # corrigé sur des pages séparées
    footer = _footer(exam)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


if __name__ == "__main__":
    import logging
    import sys
    from pathlib import Path

    from app.phase4_exam.generator import generate_exam

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    course = sys.argv[1] if len(sys.argv) > 1 else "Chapter1_Part_1"
    fmt = sys.argv[2] if len(sys.argv) > 2 else "complet"

    exam = generate_exam(course, fmt, 20, "moyen")
    out = Path("exam_test.pdf")
    out.write_bytes(render_exam_pdf(exam, include_answers=True))
    print(f"✅ PDF créé : {out.resolve()} ({exam.question_count} questions, {exam.total_points:g}/20)")