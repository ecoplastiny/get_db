import requests
import json
import re
import os
import time

URL = "https://ymnik.kz/js/reque.php"
HOME_URL = "https://ymnik.kz/tests/geography/"
SAVE_EVERY = 20

LANGUAGES = [
    ("1", "RUS"),  # Russian
    ("2", "KAZ"),  # Kazakh (or whatever lang 2 is)
]

CATEGORIES = [
    ("4", "biology"),
    ("6", "math"),
    ("8", "physics"),
    ("9", "world_history"),
    ("10", "english"),
    ("13", "chemistry"),
    ("14", "chop"),
    ("1", "math_literacy"),
    ("2", "reading_literacy"),
]

def strip_html(text):
    return re.sub(r"<[^>]+>", "", text).strip()

def save(questions, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    print(f"  💾 Saved {len(questions)} → {filename}")

def make_session():
    s = requests.Session()
    s.headers.update({
        "Referer": HOME_URL,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Origin": "https://ymnik.kz",
    })
    s.get(HOME_URL, timeout=10)
    print(f"  🍪 New session: { {k: v for k, v in s.cookies.items()} }")
    return s

def is_valid_response(data):
    return (
        isinstance(data, dict)
        and "sucess" in data
        and data["sucess"].get("unical")
    )

def get_total(data):
    """Extract total questions from message like 'Вы ответили на 2 вопроса из 4671'"""
    msg = data.get("message", "")
    match = re.search(r"из (\d+)", msg)
    return int(match.group(1)) if match else 5000  # fallback to 5000 if not found

session = make_session()

for lang_id, lang_name in LANGUAGES:
    for cat_id, cat_name in CATEGORIES:
        output_file = f"{cat_name}_{lang_name}_questions.json"

        # Resume support per category
        if os.path.exists(output_file):
            with open(output_file, "r", encoding="utf-8") as f:
                questions = json.load(f)
            start_from = len(questions)
            print(f"\n📂 Resuming {cat_name} from {start_from + 1}...")
        else:
            questions = []
            start_from = 0
            print(f"\n🚀 Starting {cat_name}...")

        start_time = time.time()
        errors = 0
        total_questions = None  # will be set from first response

        i = start_from
        while True:
            try:
                # Step 1: Get question
                question_resp = session.post(URL, data={
                    "category": f'["{cat_id}"]',
                    "lang": "1",
                    "action": "new",
                }, timeout=5).json()

                # Detect total from first response
                if total_questions is None:
                    total_questions = get_total(question_resp)
                    print(f"  📊 Total questions in {cat_name}: {total_questions}")

                # Detect session expiry
                if not is_valid_response(question_resp):
                    print(f"\n  ⚠️  Session expired at q{i+1}, renewing...")
                    save(questions, output_file)
                    session = make_session()
                    time.sleep(2)
                    continue

                success = question_resp.get("sucess", {})
                unical = success.get("unical")
                answers = success.get("a", {}).get("rows", {})

                # Step 2: Submit dummy answer
                vote_resp = session.post(URL, data={
                    "vote": unical,
                    unical: '["1"]',
                }, timeout=3).json()

                correct = vote_resp.get("sucess", {}).get("good", [])

                questions.append({
                    "index": i + 1,
                    "unical": unical,
                    "question": strip_html(success.get("v", "")),
                    "answers": answers,
                    "correct": correct,
                })

                print(f"Q{i+1}/{total_questions} [{cat_name}]: {strip_html(success.get('v', ''))[:55]}... → {correct} ({answers.get(correct, '?')})")

                errors = 0
                i += 1

                if i % SAVE_EVERY == 0:
                    save(questions, output_file)
                    elapsed = time.time() - start_time
                    rate = (i - start_from) / elapsed
                    eta = (total_questions - i) / rate
                    print(f"  ⚡ {rate:.1f} q/s — ETA: {eta/60:.1f} min\n")

                # ── Check if category is done ────────────────────────────────────
                if total_questions and i >= total_questions:
                    print(f"\n✅ Done with {cat_name}! ({i} questions)")
                    save(questions, output_file)
                    session = make_session()  # fresh session for next category
                    break

            except KeyboardInterrupt:
                print(f"\n⛔ Interrupted! Saving and renewing session...")
                save(questions, output_file)
                session = make_session()
                time.sleep(2)
                # continue from where we left off

            except Exception as e:
                errors += 1
                print(f"  ❌ Error #{errors} at q{i+1}: {e}")
                save(questions, output_file)
                if errors >= 5:
                    print("  Too many errors, renewing session...")
                    session = make_session()
                    errors = 0
                time.sleep(errors * 2)

print("\n🎉 All categories done!")