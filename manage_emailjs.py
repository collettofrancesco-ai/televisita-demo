#!/usr/bin/env python3
"""Gestisce la catena di account EmailJS di riserva (DEFAULT_EMAILJS_CONFIGS) usata per
inviare le email reali ai pazienti, senza dover modificare il sorgente a mano: aggiunge,
sostituisce o elimina un account nella catena, poi ricostruisce docs/index.html e (a
richiesta) fa commit e push.

La catena è condivisa da entrambe le strutture: oggi inviano entrambe dagli stessi account
di fabbrica. Quando ciascuna struttura avrà la propria casella email reale, instradare per
struttura richiederà un cambio più ampio (collegare l'invio a S.role) — questo script gestisce
la catena di riserva così com'è oggi, account dopo account, in ordine di priorità.

Uso: python3 manage_emailjs.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "televisita_fix.html"


def find_configs_block(text):
    pattern = re.compile(r"(const\s+DEFAULT_EMAILJS_CONFIGS\s*=\s*\[)(.*?)(\n(\s*)\];)", re.S)
    match = pattern.search(text)
    if not match:
        raise ValueError("Non trovo DEFAULT_EMAILJS_CONFIGS nel sorgente.")
    return match


def get_items(block_text):
    return re.findall(r"\{[^\n]*\}", block_text)


def list_configs(text):
    match = find_configs_block(text)
    return get_items(match.group(2))


def rebuild_block(text, match, new_items):
    item_indent = match.group(4) + " " * 4
    new_block = "\n" + item_indent + (",\n" + item_indent).join(it.rstrip(",") for it in new_items)
    return text[: match.start(2)] + new_block + text[match.end(2):]


def add_config(text, config_line):
    match = find_configs_block(text)
    items = get_items(match.group(2))
    items.append(config_line.strip().rstrip(","))
    return rebuild_block(text, match, items)


def replace_config(text, index, config_line):
    match = find_configs_block(text)
    items = get_items(match.group(2))
    if index < 0 or index >= len(items):
        raise ValueError(f"Indice non valido: ci sono {len(items)} account nella catena (0-{len(items) - 1}).")
    items[index] = config_line.strip().rstrip(",")
    return rebuild_block(text, match, items)


def remove_config(text, index):
    match = find_configs_block(text)
    items = get_items(match.group(2))
    if index < 0 or index >= len(items):
        raise ValueError(f"Indice non valido: ci sono {len(items)} account nella catena (0-{len(items) - 1}).")
    if len(items) == 1:
        raise ValueError("Non posso eliminare l'unico account rimasto: l'app smetterebbe di inviare email reali.")
    del items[index]
    return rebuild_block(text, match, items)


def build_config_line(public_key, service_id, template_id):
    esc = lambda s: s.replace("'", "\\'")
    return f"{{ publicKey: '{esc(public_key)}', serviceId: '{esc(service_id)}', templateId: '{esc(template_id)}' }}"


def run(cmd, **kwargs):
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True, **kwargs)


def main():
    print("=== Gestione account EmailJS (catena di riserva) ===")
    text = SRC.read_text(encoding="utf-8")
    configs = list_configs(text)

    print(f"\nAccount attualmente nella catena, in ordine di priorità ({len(configs)}):")
    for i, c in enumerate(configs):
        print(f"  [{i}] {c}")

    print("\n1) Aggiungi un nuovo account in fondo alla catena")
    print("2) Sostituisci un account esistente")
    print("3) Elimina un account esistente")
    choice = input("\nScegli (1/2/3): ").strip()
    if choice not in ("1", "2", "3"):
        sys.exit("Scelta non valida.")

    if choice in ("1", "2"):
        print("\nInserisci i dati dell'account EmailJS (li trovi sulla dashboard di EmailJS):")
        public_key = input("Public Key: ").strip()
        service_id = input("Service ID: ").strip()
        template_id = input("Template ID: ").strip()
        if not (public_key and service_id and template_id):
            sys.exit("Tutti i campi sono obbligatori.")
        config_line = build_config_line(public_key, service_id, template_id)

    try:
        if choice == "1":
            new_text = add_config(text, config_line)
            action_desc = "Aggiungo un nuovo account alla catena di riserva EmailJS"
        elif choice == "2":
            index = int(input(f"\nIndice da sostituire (0-{len(configs) - 1}): ").strip())
            new_text = replace_config(text, index, config_line)
            action_desc = f"Sostituisco l'account EmailJS in posizione {index}"
        else:
            index = int(input(f"\nIndice da eliminare (0-{len(configs) - 1}): ").strip())
            new_text = remove_config(text, index)
            print(f"\nATTENZIONE: stai per eliminare l'account in posizione {index} dalla catena di riserva.")
            action_desc = f"Elimino l'account EmailJS in posizione {index}"
    except ValueError as e:
        sys.exit(str(e))

    print(f"\n{action_desc}.")
    confirm = input("Confermi e applico la modifica al sorgente? (s/n): ").strip().lower()
    if confirm != "s":
        sys.exit("Operazione annullata, nessuna modifica fatta.")

    backup_path = SRC.with_suffix(SRC.suffix + ".bak")
    backup_path.write_text(text, encoding="utf-8")
    print(f"Copia di sicurezza salvata in {backup_path.name} (versione precedente alla modifica).")

    SRC.write_text(new_text, encoding="utf-8")
    print(f"Modifica applicata a {SRC.name}.")

    print("\nRicostruisco la build minificata...")
    run([sys.executable, "build_minified.py"])

    print("\nModifiche pronte. Vuoi pubblicarle subito (commit + push)?")
    confirm_push = input("(s/n): ").strip().lower()
    if confirm_push != "s":
        print("Fatto qui: le modifiche sono nei file ma non sono state pubblicate.")
        print("Per pubblicarle più avanti: git add -A && git commit -m \"...\" && git push")
        return

    run(["git", "add", "televisita_fix.html", "docs/index.html"])
    run(["git", "commit", "-m", action_desc])
    run(["git", "push"])
    print(f"\nFatto: {action_desc}. Il sito si aggiornerà su GitHub Pages tra qualche minuto.")


if __name__ == "__main__":
    main()
