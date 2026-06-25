#!/usr/bin/env python3
"""Controlli di salute rapidi per Olovisita, da lanciare prima di un push importante:
verifica che le traduzioni IT/FR siano complete e che la build pubblicata
(docs/index.html) sia davvero sincronizzata con il sorgente e online su GitHub Pages.

Uso: python3 check_health.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "televisita_fix.html"
DIST = ROOT / "docs" / "index.html"
GH_REPO = "collettofrancesco-ai/olovisita"


def extract_lang_block(text, lang, start_from=0):
    """Estrae il testo di LANGS.<lang> = { ... } contando le parentesi: alcuni valori
    contengono `{` e `}` dentro l'HTML (es. <strong>...</strong> con altre parentesi annidate),
    quindi una regex senza bilanciamento rischierebbe di fermarsi alla chiusura sbagliata."""
    marker = re.search(r"\b" + lang + r":\s*\{", text[start_from:])
    if not marker:
        raise ValueError(f"Non trovo il blocco LANGS.{lang} nel sorgente.")
    start = start_from + marker.end() - 1
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise ValueError(f"Parentesi non bilanciate nel blocco LANGS.{lang}.")


def extract_keys(block_text):
    # I valori possono essere tra virgolette singole, doppie o backtick (stringhe multilinea
    # con markup HTML, es. pdf_consent_body): vanno riconosciute tutte e tre le forme.
    return set(re.findall(r"(?m)^\s*([a-zA-Z_][a-zA-Z0-9_]*):\s*[\"'`]", block_text))


def extract_used_keys(text):
    # Trova solo gli usi STATICI (chiave scritta letteralmente nel codice). Chiavi costruite
    # dinamicamente (es. 'spec_' + qualcosa.toLowerCase()) non possono essere viste da un
    # controllo a regex: è un limite noto di questo script, non una garanzia di completezza assoluta.
    used = set()
    used |= set(re.findall(r"\bt\(\s*['\"]([a-zA-Z_][a-zA-Z0-9_]*)['\"]", text))
    used |= set(re.findall(r'data-i18n(?:-holder)?="([a-zA-Z_][a-zA-Z0-9_]*)"', text))
    return used


def check_translations(text):
    print("=== Controllo traduzioni IT/FR ===")
    anchor = re.search(r"const\s+LANGS\s*=\s*\{", text)
    if not anchor:
        print("❌ Non trovo l'oggetto LANGS nel sorgente: controllo annullato.")
        return False

    it_keys = extract_keys(extract_lang_block(text, "it", anchor.start()))
    fr_keys = extract_keys(extract_lang_block(text, "fr", anchor.start()))
    used_keys = extract_used_keys(text)

    missing_in_it = sorted(used_keys - it_keys)
    missing_in_fr = sorted(used_keys - fr_keys)
    unused = sorted((it_keys | fr_keys) - used_keys)

    print(f"Chiavi usate nel codice (trovate staticamente): {len(used_keys)}")
    print(f"Chiavi definite in IT: {len(it_keys)} — in FR: {len(fr_keys)}")
    print()

    if missing_in_it:
        print(f"❌ Usate ma MAI definite in italiano ({len(missing_in_it)}) — comparirebbe il nome grezzo della chiave a schermo:")
        for k in missing_in_it:
            print(f"   - {k}")
    else:
        print("✅ Nessuna chiave usata manca dalla lista italiana.")

    print()
    if missing_in_fr:
        print(f"⚠️  Usate ma MAI definite in francese ({len(missing_in_fr)}) — chi usa l'app in francese vedrebbe il testo italiano al loro posto:")
        for k in missing_in_fr:
            print(f"   - {k}")
    else:
        print("✅ Nessuna chiave usata manca dalla lista francese.")

    print()
    print(f"ℹ️  Chiavi definite ma non trovate in uso da nessuna parte: {len(unused)}")
    print("   (non è necessariamente un problema: alcune chiavi vengono costruite dinamicamente nel")
    print("   codice — es. 'spec_' + qualcosa — e questo controllo statico non riesce a vederle.)")

    return not missing_in_it  # solo le mancanze in IT sono davvero bloccanti


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def check_build_and_deploy():
    print("\n=== Controllo build + pubblicazione ===")

    before = DIST.read_text(encoding="utf-8") if DIST.exists() else None
    print("Ricostruisco docs/index.html dal sorgente attuale...")
    result = run([sys.executable, "build_minified.py"])
    if result.returncode != 0:
        print("❌ La build è FALLITA:")
        print(result.stderr)
        return False
    print(result.stdout.strip())

    after = DIST.read_text(encoding="utf-8")
    if before != after:
        print("⚠️  docs/index.html NON era aggiornato rispetto al sorgente: l'ho appena rigenerato ora.")
        print("   Ricordati di fare commit + push di questa modifica.")
    else:
        print("✅ docs/index.html era già perfettamente sincronizzato col sorgente.")

    git_status = run(["git", "status", "--short"]).stdout.strip()
    if git_status:
        print("\nℹ️  Ci sono modifiche locali non ancora committate:")
        print(git_status)
    else:
        print("\n✅ Nessuna modifica locale in sospeso.")

    unpushed = run(["git", "log", "--oneline", "origin/main..HEAD"]).stdout.strip()
    if unpushed:
        print("\n⚠️  Ci sono commit locali non ancora pubblicati (git push):")
        print(unpushed)
    else:
        print("✅ Tutti i commit locali sono già stati pubblicati su GitHub.")

    print("\nControllo lo stato della pubblicazione su GitHub Pages...")
    # L'endpoint /pages/builds/latest a volte resta "indietro" per diversi minuti rispetto alla
    # situazione reale (verificato il 25/06/2026: segnalava un commit vecchio anche con la build
    # GitHub Actions già conclusa con successo su quello nuovo). L'elenco delle run del workflow
    # "pages build and deployment" è il segnale affidabile: è lo stesso processo che pubblica
    # davvero il sito, quindi diciamo che è online solo quando QUELLO conferma il commit giusto.
    gh_result = run([
        "gh", "run", "list", "--repo", GH_REPO,
        "--workflow=pages-build-deployment", "--limit", "1",
        "--json", "headSha,status,conclusion"
    ])
    if gh_result.returncode != 0:
        print("❌ Non sono riuscito a contattare GitHub (serve 'gh auth login' e una connessione attiva):")
        print(gh_result.stderr.strip())
        return False

    runs = json.loads(gh_result.stdout)
    local_head = run(["git", "rev-parse", "HEAD"]).stdout.strip()

    if not runs:
        print("⚠️  Nessuna esecuzione del workflow di pubblicazione trovata.")
        return True

    latest = runs[0]
    deployed_sha = latest.get("headSha")
    run_status = latest.get("status")
    conclusion = latest.get("conclusion")

    if run_status != "completed":
        print(f"⚠️  La pubblicazione è ancora in corso (stato: {run_status}): aspetta qualche minuto e riprova.")
    elif conclusion != "success":
        print(f"❌ L'ultima pubblicazione è FALLITA (esito: {conclusion}). Controlla su GitHub cosa è andato storto.")
    elif deployed_sha == local_head:
        print("✅ Il sito pubblicato corrisponde esattamente all'ultimo commit locale.")
    else:
        print(f"⚠️  L'ultima pubblicazione riuscita riguarda un commit diverso da quello locale (online: {deployed_sha[:8]}, locale: {local_head[:8]}).")
        print("   Probabilmente c'è un push recente non ancora arrivato qui, o viceversa.")

    return True


def main():
    print("=== Controllo di salute Olovisita ===")
    print("1) Controllo traduzioni IT/FR")
    print("2) Verifica build + pubblicazione")
    print("3) Entrambi")
    choice = input("Scegli (1/2/3): ").strip()
    if choice not in ("1", "2", "3"):
        sys.exit("Scelta non valida.")

    text = SRC.read_text(encoding="utf-8")

    ok = True
    if choice in ("1", "3"):
        ok = check_translations(text) and ok
    if choice in ("2", "3"):
        ok = check_build_and_deploy() and ok

    print("\n" + ("✅ Tutto a posto." if ok else "❌ Ci sono problemi da controllare (vedi sopra)."))


if __name__ == "__main__":
    main()
