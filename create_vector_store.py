#!/usr/bin/env python3
"""
create_vector_store.py
Erstellt einen OpenAI Vector Store aus ChatGPT-Gesprächsdaten.

Unterstützte Formate:
  - Offizieller ChatGPT-Export (conversations.json mit mapping-Struktur)
  - GPT2Claude Migration Kit / ChatGPT All Conversations Extension

Voraussetzung:
  pip install openai
  export OPENAI_API_KEY='sk-...'

Verwendung:
  python create_vector_store.py
  python create_vector_store.py meine_datei.json
"""

import json
import os
import sys
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("Fehler: OpenAI-Bibliothek nicht installiert.")
    print("Bitte ausführen: pip install openai")
    sys.exit(1)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("Fehler: OPENAI_API_KEY ist nicht gesetzt.")
    print("Bitte ausführen: export OPENAI_API_KEY='sk-...'")
    sys.exit(1)

client = OpenAI(api_key=OPENAI_API_KEY)

CHUNK_CHARS = 2500   # ~600 Tokens (1 Token ≈ 4 Zeichen)
BATCH_SIZE  = 20     # Dateien pro Upload-Batch (konservativ für Rate Limits)


# ─── Format-Erkennung & Parsing ───────────────────────────────────────────────

def format_ts(ts):
    if not ts:
        return "Unbekannt"
    try:
        if isinstance(ts, (int, float)) and ts > 1_000_000:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        return str(ts)[:16]
    except Exception:
        return str(ts)


def parse_official_format(conversations: list) -> list:
    """Offizieller ChatGPT-Export: Array mit mapping-Knoten."""
    result = []
    for conv in conversations:
        if not isinstance(conv, dict):
            continue
        title      = conv.get("title", "Ohne Titel")
        create_time = conv.get("create_time", 0)
        mapping    = conv.get("mapping", {})

        messages = []
        for node in mapping.values():
            msg = node.get("message")
            if not msg:
                continue
            role = msg.get("author", {}).get("role", "")
            if role not in ("user", "assistant"):
                continue
            parts = msg.get("content", {}).get("parts", [])
            text  = " ".join(str(p) for p in parts if p and isinstance(p, str)).strip()
            if not text:
                continue
            messages.append({
                "role":    role,
                "content": text,
                "time":    msg.get("create_time", create_time),
            })

        messages.sort(key=lambda m: m.get("time") or 0)
        if messages:
            result.append({"title": title, "create_time": create_time, "messages": messages})
    return result


def parse_alternative_format(data) -> list:
    """GPT2Claude / ChatGPT All Conversations Extension / andere Formate."""
    convs = data if isinstance(data, list) else data.get("conversations", [])
    result = []
    for conv in convs:
        if not isinstance(conv, dict):
            continue
        title       = conv.get("title") or conv.get("name") or "Ohne Titel"
        create_time = conv.get("created_at") or conv.get("create_time") or 0
        raw_msgs    = conv.get("messages") or conv.get("turns") or []

        messages = []
        for msg in raw_msgs:
            role = msg.get("role") or msg.get("author") or ""
            if role not in ("user", "assistant"):
                continue
            content = msg.get("content") or msg.get("text") or ""
            if isinstance(content, list):
                content = " ".join(str(p) for p in content if p)
            content = str(content).strip()
            if not content:
                continue
            messages.append({
                "role":    role,
                "content": content,
                "time":    msg.get("timestamp") or msg.get("create_time") or 0,
            })

        if messages:
            result.append({"title": title, "create_time": create_time, "messages": messages})
    return result


def detect_and_parse(data) -> list:
    if isinstance(data, list) and data:
        if "mapping" in data[0]:
            print("Format erkannt: Offizieller ChatGPT-Export (mapping)")
            return parse_official_format(data)
        else:
            print("Format erkannt: GPT2Claude / alternatives Listen-Format")
            return parse_alternative_format(data)
    if isinstance(data, dict):
        if "conversations" in data:
            print("Format erkannt: GPT2Claude Migration Kit (Objekt)")
            return parse_alternative_format(data)
        if "mapping" in data:
            return parse_official_format([data])
    print("Warnung: Format unbekannt – versuche allgemeines Parsing")
    return parse_alternative_format(data)


# ─── Chunking ─────────────────────────────────────────────────────────────────

def chunk_conversation(conv: dict) -> list:
    title    = conv["title"]
    date_str = format_ts(conv["create_time"])
    header   = f"Gespräch: {title}\nDatum: {date_str}\n\n"
    chunks   = []
    current  = header

    for msg in conv["messages"]:
        label = "Nutzer" if msg["role"] == "user" else "Assistent"
        line  = f"[{format_ts(msg.get('time'))}] {label}: {msg['content']}\n\n"

        if len(current) + len(line) > CHUNK_CHARS and len(current) > len(header) + 50:
            chunks.append(current.strip())
            current = f"Gespräch: {title}\nDatum: {date_str}\n(Fortsetzung)\n\n"

        current += line

    if len(current.strip()) > len(header.strip()) + 10:
        chunks.append(current.strip())

    return chunks


# ─── Upload ───────────────────────────────────────────────────────────────────

def upload_batch(vector_store_id: str, texts: list, batch_num: int, total: int) -> int:
    print(f"  Batch {batch_num}/{total} – {len(texts)} Dateien ...", end=" ", flush=True)
    files = [
        (f"chunk_{batch_num}_{i}.txt", BytesIO(t.encode("utf-8")), "text/plain")
        for i, t in enumerate(texts)
    ]
    try:
        result = client.beta.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store_id,
            files=files,
        )
        done = result.file_counts.completed
        print(f"OK ({done} hochgeladen, Status: {result.status})")
        return done
    except Exception as e:
        print(f"FEHLER: {e}")
        return 0


# ─── Hauptprogramm ────────────────────────────────────────────────────────────

def main():
    # Datei bestimmen
    json_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("conversations.json")
    if not json_path.exists():
        found = list(Path(".").rglob("conversations.json"))
        if found:
            json_path = found[0]
            print(f"Datei gefunden: {json_path}")
        else:
            print("Fehler: conversations.json nicht gefunden.")
            print("Tipp: Datei in denselben Ordner wie das Skript legen,")
            print("      oder Pfad als Argument übergeben:")
            print("      python create_vector_store.py /pfad/zur/datei.json")
            sys.exit(1)

    # Laden
    print(f"Lade {json_path} ...")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Parsen
    conversations = detect_and_parse(data)
    print(f"{len(conversations)} Gespräche gefunden.\n")
    if not conversations:
        print("Keine Gespräche gefunden – bitte Format prüfen.")
        sys.exit(1)

    # Chunking
    print("Teile Gespräche in Chunks auf ...")
    all_chunks = []
    for i, conv in enumerate(conversations, 1):
        all_chunks.extend(chunk_conversation(conv))
        if i % 100 == 0 or i == len(conversations):
            print(f"  {i}/{len(conversations)} Gespräche → {len(all_chunks)} Chunks")

    print(f"\nErgebnis: {len(all_chunks)} Chunks aus {len(conversations)} Gesprächen")
    print(f"Geschätzter Speicher: ~{len(all_chunks) * CHUNK_CHARS // 1024} KB\n")

    # Vector Store erstellen
    store_name = f"ChatGPT-Gedaechtnis-{datetime.now().strftime('%Y-%m-%d')}"
    print(f"Erstelle Vector Store '{store_name}' ...")
    store = client.beta.vector_stores.create(name=store_name)
    vector_store_id = store.id
    print(f"Vector Store ID: {vector_store_id}\n")

    # Batches hochladen
    batches = [all_chunks[i:i + BATCH_SIZE] for i in range(0, len(all_chunks), BATCH_SIZE)]
    print(f"Lade {len(all_chunks)} Chunks in {len(batches)} Batches hoch ...")
    total_ok = 0
    for num, batch in enumerate(batches, 1):
        total_ok += upload_batch(vector_store_id, batch, num, len(batches))
        time.sleep(0.3)  # sanftes Rate-Limiting

    # Abschlussbericht
    print("\n" + "=" * 55)
    print("  FERTIG!")
    print("=" * 55)
    print(f"  Gespräche verarbeitet : {len(conversations)}")
    print(f"  Chunks erstellt       : {len(all_chunks)}")
    print(f"  Dateien hochgeladen   : {total_ok}")
    print()
    print("  Vector Store ID:")
    print(f"    {vector_store_id}")
    print()
    print("  Jetzt in Netlify eintragen:")
    print("  Site Settings → Environment Variables → Add variable")
    print("    Schlüssel : MEMORY_VECTOR_STORE_ID")
    print(f"    Wert      : {vector_store_id}")
    print("=" * 55)


if __name__ == "__main__":
    main()
