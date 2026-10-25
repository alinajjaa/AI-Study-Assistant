"""Usage de Claude Code sur le projet, à partir des sessions JSONL enregistrées localement.

Usage :
    python scripts/claude_usage.py [--dir <dossier des sessions>] [--csv sessions.csv] [--csv-prompts demandes.csv]
                                   [--md rapport.md]

Dossier par défaut : ~/.claude/projects/<chemin du projet encodé> (ex. c--Users-<nom>-study-companion).

Par session : dates, demande résumée, tours (demandes de l'utilisateur), appels à l'API, jetons d'entrée, de
sortie et de cache, modèles, durée, lignes ajoutées (compteur de Claude Code), outils utilisés.
Par demande : les mêmes mesures, réparties entre les demandes successives d'une session.

Règles de lecture :
- un message de l'assistant est écrit sur plusieurs lignes (une par bloc de contenu) avec le même identifiant et
  le même usage : il n'est compté qu'une fois ;
- les lignes « cost-state » sont cumulatives dans une session : seule la dernière est gardée ;
- aucun texte n'est recopié tel quel : la demande est résumée (140 caractères) et passée par un masquage des
  emails, des clés d'API et des jetons.
"""
import argparse
import csv
import glob
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

ACTIVE_GAP_S = 15 * 60  # au-delà de 15 min sans événement, la session est considérée en pause

SECRETS = [
    re.compile(r"\b(gsk|hf|sk|pk|ghp|gho|github_pat|xox[bap])[_-][A-Za-z0-9_-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"),  # JWT
    re.compile(r"(?i)\b([A-Z_]*(?:SECRET|TOKEN|API_KEY|PASSWORD)[A-Z_]*)\s*[=:]\s*\S+"),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
]
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
TEST_COMMAND = re.compile(r"pytest|ng test|ng build|vitest|npm (run )?(test|build)")
# Le drapeau is_error n'est presque jamais posé sur un résultat de commande : l'échec se lit dans la sortie
TEST_FAILURE = re.compile(r"\b[1-9]\d* failed|FAILED |error TS\d+|✘ \[ERROR\]|ERROR in |"
                          r"Application bundle generation failed|Exit code [1-9]")


def mask(text: str) -> str:
    text = EMAIL.sub("[EMAIL]", text)
    for pattern in SECRETS:
        text = pattern.sub(lambda m: (m.group(1) + "=[MASQUÉ]") if m.re.pattern.startswith("(?i)") else "[MASQUÉ]",
                           text)
    return text


def summarize_request(text: str, limit: int = 140) -> str:
    """Résumé d'une demande : la ligne « Objectif » si elle existe, sinon la première ligne utile."""
    text = re.sub(r"<ide_[a-z_]+>.*?</ide_[a-z_]+>", " ", text, flags=re.S)
    text = re.sub(r"</?pasted_content[^>]*>", " ", text)
    flat = " ".join(re.sub(r"^[ \t]*[-•]+[ \t]*|^-{3,}$", "", text, flags=re.M).split())
    goal = re.search(r"\bObjectif[^:]{0,30}:\s*(.+?)(?:\.\s|\s\d\.\s|$)", flat)
    if goal:
        first = goal.group(1)
    else:  # première phrase qui n'est ni le contexte ni une règle
        sentences = re.split(r"(?<=[.!?])\s+", flat)
        skip = ("contexte", "rôle", "n'exécute", "règles", "ne modifie", "ne change")
        first = next((s for s in sentences if not s.lower().startswith(skip)), sentences[0] if sentences else "")
    first = mask(first.strip())
    return first if len(first) <= limit else first[:limit - 1].rstrip() + "…"


def user_text(message: dict) -> str | None:
    """Texte d'une demande de l'utilisateur ; None pour un résultat d'outil."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    texts = []
    for block in content or []:
        if block.get("type") == "tool_result":
            return None
        if block.get("type") == "text":
            texts.append(block["text"])
    return "\n".join(texts)


def is_human_request(text: str) -> bool:
    noise = ("<local-command", "<command-name>", "<task-notification>", "[Request interrupted",
             "This session is being continued from a previous conversation", "<system-reminder>")
    return bool(text.strip()) and not text.lstrip().startswith(noise)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class Usage:
    api_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation: int = 0
    cache_read: int = 0
    tools: dict = field(default_factory=dict)
    lines_written: int = 0  # lignes des contenus écrits par Write et Edit (new_string)
    test_runs: int = 0
    test_failures: int = 0

    def add_message(self, usage: dict) -> None:
        self.api_calls += 1
        self.input_tokens += usage.get("input_tokens") or 0
        self.output_tokens += usage.get("output_tokens") or 0
        self.cache_creation += usage.get("cache_creation_input_tokens") or 0
        self.cache_read += usage.get("cache_read_input_tokens") or 0

    @property
    def total_input(self) -> int:
        return self.input_tokens + self.cache_creation + self.cache_read


@dataclass
class Request:
    timestamp: str
    summary: str
    chars: int
    usage: Usage = field(default_factory=Usage)
    events: list = field(default_factory=list)


@dataclass
class Session:
    session_id: str
    requests: list = field(default_factory=list)
    timestamps: list = field(default_factory=list)
    models: set = field(default_factory=set)
    cost_state: dict | None = None
    resumes: int = 0
    compactions: int = 0

    @property
    def usage(self) -> Usage:
        total = Usage()
        for r in self.requests:
            u = r.usage
            for name in ("api_calls", "input_tokens", "output_tokens", "cache_creation", "cache_read",
                         "lines_written", "test_runs", "test_failures"):
                setattr(total, name, getattr(total, name) + getattr(u, name))
            for tool, n in u.tools.items():
                total.tools[tool] = total.tools.get(tool, 0) + n
        return total


def active_seconds(timestamps: list[str]) -> float:
    times = sorted(parse_time(t) for t in timestamps)
    return sum(min(gap, ACTIVE_GAP_S) for gap in
               ((b - a).total_seconds() for a, b in zip(times, times[1:])) if gap <= ACTIVE_GAP_S)


def read_session(path: str) -> Session:
    session = Session(session_id=os.path.basename(path).removesuffix(".jsonl"))
    seen_messages: dict[str, Request] = {}
    pending_tests: dict[str, Request] = {}
    current: Request | None = None

    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = d.get("type")
            if d.get("timestamp"):
                session.timestamps.append(d["timestamp"])
            if kind == "cost-state":
                session.cost_state = d
                continue
            if d.get("isSidechain"):
                continue

            if kind == "user" and not d.get("isMeta"):
                text = user_text(d["message"])
                if text is None:  # résultats d'outils : échecs des tests et builds
                    for block in d["message"]["content"]:
                        if block.get("type") == "tool_result" and block.get("tool_use_id") in pending_tests:
                            req = pending_tests.pop(block["tool_use_id"])
                            output = block.get("content")
                            if not isinstance(output, str):
                                output = " ".join(x.get("text", "") for x in output or [] if isinstance(x, dict))
                            if block.get("is_error") or TEST_FAILURE.search(output):
                                req.usage.test_failures += 1
                    continue
                if "This session is being continued from a previous conversation" in text:
                    session.resumes += 1
                    continue
                if "<command-name>/compact" in text:
                    session.compactions += 1
                    continue
                if is_human_request(text):
                    current = Request(timestamp=d["timestamp"], summary=summarize_request(text), chars=len(text))
                    session.requests.append(current)
                if current and d.get("timestamp"):
                    current.events.append(d["timestamp"])

            elif kind == "assistant":
                message = d.get("message", {})
                model = message.get("model")
                if not model or model == "<synthetic>":
                    continue
                if current is None:  # session reprise sans nouvelle demande
                    current = Request(timestamp=d["timestamp"], summary="(suite d'une session précédente)", chars=0)
                    session.requests.append(current)
                current.events.append(d["timestamp"])
                session.models.add(model)
                message_id = message.get("id")
                if message_id not in seen_messages:
                    seen_messages[message_id] = current
                    current.usage.add_message(message.get("usage") or {})
                for block in message.get("content") or []:
                    if block.get("type") != "tool_use":
                        continue
                    name = block.get("name", "?")
                    current.usage.tools[name] = current.usage.tools.get(name, 0) + 1
                    args = block.get("input") or {}
                    if name == "Write":
                        current.usage.lines_written += len(str(args.get("content", "")).splitlines())
                    elif name == "Edit":
                        current.usage.lines_written += len(str(args.get("new_string", "")).splitlines())
                    elif name in ("Bash", "PowerShell") and TEST_COMMAND.search(str(args.get("command", ""))):
                        current.usage.test_runs += 1
                        pending_tests[block.get("id")] = current
    return session


def default_dir() -> str:
    project = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    encoded = re.sub(r"[:\\/]", "-", project)
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", encoded)


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def session_row(s: Session) -> dict:
    u = s.usage
    cost = s.cost_state or {}
    by_model = dict(cost.get("modelUsage") or {})
    side_models = ", ".join(sorted(m for m in by_model if m not in s.models))
    start, end = min(s.timestamps), max(s.timestamps)
    return {
        "session": s.session_id[:8],
        "debut": start[:16].replace("T", " "),
        "fin": end[:16].replace("T", " "),
        "demande": s.requests[0].summary if s.requests else "",
        "tours": len([r for r in s.requests if r.chars]),
        "reprises": s.resumes,
        "compactions": s.compactions,
        "appels_api": u.api_calls,
        "jetons_entree": u.input_tokens,
        "jetons_cache_ecriture": u.cache_creation,
        "jetons_cache_lecture": u.cache_read,
        "jetons_sortie": u.output_tokens,
        "modeles": ", ".join(sorted(s.models)),
        "modeles_annexes": side_models,
        "duree_active_min": round(active_seconds(s.timestamps) / 60, 1),
        "duree_api_min": round(cost.get("totalAPIDuration", 0) / 60000, 1) if cost else "",
        "lignes_ajoutees": cost.get("totalLinesAdded", "") if cost else "",
        "lignes_supprimees": cost.get("totalLinesRemoved", "") if cost else "",
        "lignes_ecrites_outils": u.lines_written,
        "edit_write": u.tools.get("Edit", 0) + u.tools.get("Write", 0),
        "commandes": u.tools.get("Bash", 0) + u.tools.get("PowerShell", 0),
        "tests_builds": u.test_runs,
        "tests_builds_en_echec": u.test_failures,
        "cout_api_estime_usd": round(cost.get("totalCostUSD", 0), 2) if cost else "",
    }


def request_rows(s: Session) -> list[dict]:
    rows = []
    for r in s.requests:
        u = r.usage
        rows.append({
            "session": s.session_id[:8], "date": r.timestamp[:16].replace("T", " "), "demande": r.summary,
            "caracteres": r.chars, "appels_api": u.api_calls, "jetons_entree": u.input_tokens,
            "jetons_cache_ecriture": u.cache_creation, "jetons_cache_lecture": u.cache_read,
            "jetons_sortie": u.output_tokens,
            "duree_active_min": round(active_seconds(r.events) / 60, 1) if len(r.events) > 1 else 0,
            "lignes_ecrites_outils": u.lines_written, "edit_write": u.tools.get("Edit", 0) + u.tools.get("Write", 0),
            "tests_builds": u.test_runs, "tests_builds_en_echec": u.test_failures,
        })
    return rows


def write_csv(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def markdown(sessions: list[dict], totals: dict) -> str:
    out = ["| Session | Début | Demande (résumé) | Tours | Appels API | Entrée | Cache (écriture / lecture) | Sortie "
           "| Modèle | Durée active | Lignes ajoutées |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sessions:
        out.append(f"| `{r['session']}` | {r['debut']} | {r['demande']} | {r['tours']} | {r['appels_api']} "
                   f"| {fmt_int(r['jetons_entree'])} | {fmt_int(r['jetons_cache_ecriture'])} / "
                   f"{fmt_int(r['jetons_cache_lecture'])} | {fmt_int(r['jetons_sortie'])} | {r['modeles']} "
                   f"| {r['duree_active_min']} min | {r['lignes_ajoutees']} |")
    out.append(f"| **Total** | | {totals['sessions']} sessions | {totals['tours']} | {totals['appels_api']} "
               f"| {fmt_int(totals['jetons_entree'])} | {fmt_int(totals['jetons_cache_ecriture'])} / "
               f"{fmt_int(totals['jetons_cache_lecture'])} | {fmt_int(totals['jetons_sortie'])} | "
               f"| {totals['duree_active_min']} min | {totals['lignes_ajoutees']} |")
    return "\n".join(out)


def module_rows(prompts: list[dict], mapping: dict) -> list[dict]:
    """Totaux par module : clé « session date » exacte, sinon la session seule, sinon « non rattaché »."""
    totals: dict[str, dict] = {}
    for p in prompts:
        module = mapping.get(f"{p['session']} {p['date']}") or mapping.get(p["session"]) or "Non rattaché"
        row = totals.setdefault(module, {"module": module, "demandes": 0, "appels_api": 0, "jetons_entree": 0,
                                         "jetons_cache_ecriture": 0, "jetons_cache_lecture": 0, "jetons_sortie": 0,
                                         "duree_active_min": 0.0, "lignes_ecrites_outils": 0, "tests_builds": 0,
                                         "tests_builds_en_echec": 0})
        row["demandes"] += 1
        for key in list(row)[2:]:
            row[key] += p[key]
    for row in totals.values():
        row["duree_active_min"] = round(row["duree_active_min"], 1)
    return sorted(totals.values(), key=lambda r: r["module"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", default=default_dir())
    parser.add_argument("--csv")
    parser.add_argument("--csv-prompts")
    parser.add_argument("--md")
    parser.add_argument("--modules", help="JSON {\"session date\" ou \"session\": module}")
    parser.add_argument("--csv-modules")
    args = parser.parse_args()

    paths = sorted(glob.glob(os.path.join(args.dir, "*.jsonl")))
    sessions = [s for s in (read_session(p) for p in paths) if s.timestamps and s.models]
    sessions.sort(key=lambda s: min(s.timestamps))
    rows = [session_row(s) for s in sessions]
    prompts = [row for s in sessions for row in request_rows(s)]

    numeric = ("tours", "appels_api", "jetons_entree", "jetons_cache_ecriture", "jetons_cache_lecture",
               "jetons_sortie", "edit_write", "commandes", "tests_builds", "tests_builds_en_echec",
               "lignes_ecrites_outils")
    totals = {k: sum(r[k] for r in rows) for k in numeric}
    totals["sessions"] = len(rows)
    totals["duree_active_min"] = round(sum(r["duree_active_min"] for r in rows), 1)
    totals["lignes_ajoutees"] = sum(r["lignes_ajoutees"] or 0 for r in rows)
    totals["lignes_supprimees"] = sum(r["lignes_supprimees"] or 0 for r in rows)
    totals["cout_api_estime_usd"] = round(sum(r["cout_api_estime_usd"] or 0 for r in rows), 2)

    report = markdown(rows, totals)
    print(report)
    print("\nTotaux :", json.dumps(totals, ensure_ascii=False))
    if args.csv:
        write_csv(args.csv, rows)
    if args.csv_prompts:
        write_csv(args.csv_prompts, prompts)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(report + "\n")
    if args.modules:
        with open(args.modules, encoding="utf-8") as f:
            mapping = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
        modules = module_rows(prompts, mapping)
        print("\nPar module :")
        for m in modules:
            print(f"  {m['module']}: {m['demandes']} demandes, {m['appels_api']} appels, "
                  f"sortie {fmt_int(m['jetons_sortie'])}, cache lu {fmt_int(m['jetons_cache_lecture'])}, "
                  f"{m['duree_active_min']} min, {m['lignes_ecrites_outils']} lignes")
        if args.csv_modules:
            write_csv(args.csv_modules, modules)


if __name__ == "__main__":
    main()
