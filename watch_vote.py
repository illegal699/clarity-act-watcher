"""
Sledzi glosowanie w Senacie USA nad H.R. 3633 (Digital Asset Market Clarity Act,
"CLARITY Act") i wysyla powiadomienia na Telegram, gdy:
  - znajdzie pasujace glosowanie na liscie glosowan Senatu,
  - w trakcie glosowania zmieni sie licznik glosow,
  - glosowanie sie zakonczy (wynik koncowy).

Zrodlo danych: oficjalne pliki XML Senate.gov (Legislative Information System).
Nie wymaga zadnego klucza API ani zewnetrznych bibliotek (tylko stdlib).
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# --- Konfiguracja -----------------------------------------------------------

CONGRESS = 119
SESSION = 2  # 119. Kongres, 2. sesja = rok 2026

# Slowa kluczowe do rozpoznania glosowania nad CLARITY Act na liscie glosowan.
# Dopasowanie jest case-insensitive i sprawdzane w polach issue/question/title/
# document_title/amendment_to_document_number.
KEYWORDS = ["3633", "clarity act", "digital asset market clarity"]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

LIVE_POLL_INTERVAL_SECONDS = 25
LIVE_POLL_BUDGET_SECONDS = 25 * 60  # ile najwyzej pollowac "na zywo" w jednym uruchomieniu

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ClarityActVoteWatcher/1.0; personal use script)"
}

# --- Pomocnicze: HTTP / Telegram / stan -------------------------------------


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Brak TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID - wiadomosc nie wyslana:")
        print(text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=HTTP_HEADERS)
    try:
        urllib.request.urlopen(req, timeout=15)
        print(f"[TELEGRAM] Wyslano: {text[:60]}...")
    except urllib.error.URLError as e:
        print(f"[ERROR] Wysylka na Telegram nie powiodla sie: {e}")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"notified_pending": [], "done": {}, "last_tally": {}}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# --- Parsowanie danych Senate.gov --------------------------------------------


def text_matches(*parts: str) -> bool:
    blob = " ".join(p or "" for p in parts).lower()
    return any(k in blob for k in KEYWORDS)


def fetch_vote_menu() -> list:
    url = (
        "https://www.senate.gov/legislative/LIS/roll_call_lists/"
        f"vote_menu_{CONGRESS}_{SESSION}.xml"
    )
    root = ET.fromstring(http_get(url))

    def g(node, tag):
        el = node.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    votes = []
    for v in root.iter("vote"):
        votes.append(
            {
                "number": g(v, "vote_number"),
                "date": g(v, "vote_date"),
                "issue": g(v, "issue"),
                "question": g(v, "question"),
                "title": g(v, "title"),
                "document_title": g(v, "document_title"),
                "amendment_to_document_number": g(v, "amendment_to_document_number"),
                "result": g(v, "result"),
            }
        )
    return votes


def fetch_vote_detail(number: str) -> dict:
    padded = str(number).zfill(5)
    url = (
        "https://www.senate.gov/legislative/LIS/roll_call_votes/"
        f"vote{CONGRESS}{SESSION}/vote_{CONGRESS}_{SESSION}_{padded}.xml"
    )
    root = ET.fromstring(http_get(url))

    def g(tag):
        el = root.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    count = root.find("count")

    def gc(tag):
        if count is None:
            return ""
        el = count.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    return {
        "question": g("vote_question_text"),
        "document": g("vote_document_text"),
        "result_text": g("vote_result_text"),
        "result": g("vote_result"),
        "majority": g("majority_requirement"),
        "yeas": gc("yeas"),
        "nays": gc("nays"),
        "present": gc("present"),
        "absent": gc("absent"),
    }


# --- Logika glowna ------------------------------------------------------------


def track_vote(state: dict, vote_summary: dict) -> None:
    number = vote_summary["number"]

    if state["done"].get(number):
        return

    if number not in state["notified_pending"]:
        send_telegram(
            "🔔 Znaleziono glosowanie ws. CLARITY Act (H.R. 3633)!\n"
            f"Vote #{number} ({vote_summary['date']})\n"
            f"{vote_summary['question'] or vote_summary['title']}\n"
            "Sledze wynik na zywo..."
        )
        state["notified_pending"].append(number)
        save_state(state)

    deadline = time.time() + LIVE_POLL_BUDGET_SECONDS
    last_tally = state["last_tally"].get(number)

    while time.time() < deadline:
        try:
            detail = fetch_vote_detail(number)
        except Exception as e:  # noqa: BLE001 - chcemy przetrwac chwilowe bledy sieci
            print(f"[WARN] Nie udalo sie pobrac szczegolow vote {number}: {e}")
            time.sleep(LIVE_POLL_INTERVAL_SECONDS)
            continue

        tally = (
            f"Tak: {detail['yeas']} / Nie: {detail['nays']} "
            f"(obecni bez glosu: {detail['present']}, nieobecni: {detail['absent']})"
        )

        if detail["result"]:
            result_lower = detail["result"].lower()
            icon = "✅" if ("agreed" in result_lower or "passed" in result_lower) else "❌"
            send_telegram(
                f"{icon} WYNIK GLOSOWANIA #{number}\n"
                f"{detail['question']}\n"
                f"Wymagana wiekszosc: {detail['majority'] or 'zwykla'}\n"
                f"Wynik: {detail['result_text'] or detail['result']}\n"
                f"{tally}"
            )
            state["done"][number] = True
            state["last_tally"][number] = tally
            save_state(state)
            return

        if tally != last_tally:
            send_telegram(f"📊 Trwa glosowanie #{number}:\n{tally}")
            last_tally = tally
            state["last_tally"][number] = tally
            save_state(state)

        time.sleep(LIVE_POLL_INTERVAL_SECONDS)

    print(f"[INFO] Koniec budzetu czasowego dla vote {number} w tym uruchomieniu, "
          "kolejny cykl harmonogramu wznowi sledzenie.")


def main() -> None:
    state = load_state()

    try:
        votes = fetch_vote_menu()
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] Nie udalo sie pobrac listy glosowan Senatu: {e}")
        return

    matches = [
        v
        for v in votes
        if text_matches(
            v["issue"],
            v["question"],
            v["title"],
            v["document_title"],
            v["amendment_to_document_number"],
        )
    ]

    if not matches:
        print("Brak pasujacych glosowan na razie (H.R. 3633 / CLARITY Act).")
        return

    for v in matches:
        track_vote(state, v)


if __name__ == "__main__":
    main()
