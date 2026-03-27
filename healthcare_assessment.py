import argparse
import requests
import time

API_KEY = "ak_c02f84250f3fdd7d1271735ac5017ad15ec96ca52487fe58"
BASE_URL = "https://assessment.ksensetech.com/api"
HEADERS = {"x-api-key": API_KEY, "Content-Type": "application/json"}


def get(url, retries=6, delay=2):
    # API can fail randomly so we retry a few times before giving up
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in (429, 500, 503):
                wait = delay * (attempt + 1)
                print(f"  got {resp.status_code}, waiting {wait}s and retrying...")
                time.sleep(wait)
            else:
                print(f"  unexpected status {resp.status_code}: {resp.text[:200]}")
                return None
        except Exception as ex:
            wait = delay * (attempt + 1)
            print(f"  request failed ({ex}), retrying in {wait}s...")
            time.sleep(wait)
    print(f"  gave up on {url}")
    return None


def post(url, payload, retries=5, delay=2):
    for attempt in range(retries):
        try:
            resp = requests.post(url, headers=HEADERS, json=payload, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in (429, 500, 503):
                wait = delay * (attempt + 1)
                print(f"  got {resp.status_code}, waiting {wait}s and retrying...")
                time.sleep(wait)
            else:
                print(f"  submission failed with {resp.status_code}: {resp.text[:400]}")
                return None
        except Exception as ex:
            wait = delay * (attempt + 1)
            print(f"  request failed ({ex}), retrying in {wait}s...")
            time.sleep(wait)
    print("  could not submit after all retries")
    return None


def fetch_all_patients():
    all_patients = []
    page = 1
    limit = 20

    print("\nfetching patients...\n")

    while True:
        url = f"{BASE_URL}/patients?page={page}&limit={limit}"
        data = get(url)

        if data is None:
            # skip bad pages but don't stop entirely
            page += 1
            if page > 25:
                break
            continue

        patients = data.get("data", [])
        pagination = data.get("pagination", {})
        all_patients.extend(patients)

        total = pagination.get("total", "?")
        print(f"  page {page}: got {len(patients)} patients (total so far: {len(all_patients)}/{total})")

        # stop when there are no more pages
        if not pagination.get("hasNext", False):
            break

        page += 1
        time.sleep(0.4)  # small delay to avoid hitting rate limits

    print(f"\ndone. total patients: {len(all_patients)}\n")
    return all_patients


def score_blood_pressure(bp):
    # blood pressure comes in as "120/80" format, need to split and parse both values
    if not bp or not isinstance(bp, str):
        return 0, True

    parts = bp.strip().split("/")
    if len(parts) != 2:
        return 0, True

    sys_str, dia_str = parts[0].strip(), parts[1].strip()

    # if either side is empty e.g. "150/" or "/90", treat as invalid
    if not sys_str or not dia_str:
        return 0, True

    try:
        s = float(sys_str)
        d = float(dia_str)
    except ValueError:
        return 0, True

    # check from highest risk down
    if s >= 140 or d >= 90:
        return 4, False
    if (130 <= s <= 139) or (80 <= d <= 89):
        return 3, False
    if (120 <= s <= 129) and d < 80:
        return 2, False
    if s < 120 and d < 80:
        return 1, False

    return 0, True


def score_temperature(temp):
    if temp is None or temp == "":
        return 0, True, False

    try:
        t = float(temp)
    except (ValueError, TypeError):
        return 0, True, False

    # 101+ is high fever, 99.6-100.9 is low fever, anything else is normal
    if t >= 101.0:
        return 2, False, True
    if t >= 99.6:
        return 1, False, True
    return 0, False, False


def score_age(age):
    if age is None or age == "":
        return 0, True

    try:
        a = float(age)
    except (ValueError, TypeError):
        # handles things like "fifty-three" or "unknown"
        return 0, True

    if a > 65:
        return 2, False
    if a >= 40:
        return 1, False
    return 0, False


def classify_patients(patients):
    high_risk = []
    fever_patients = []
    data_issues = []

    print("scoring patients...\n")
    print(f"{'ID':<12} {'Name':<30} {'BP':>4} {'Tmp':>3} {'Age':>3} {'Tot':>4}  Flags")
    print("-" * 75)

    for p in patients:
        pid = p.get("patient_id", "UNKNOWN")
        name = p.get("name", "")

        bp_score, bp_invalid = score_blood_pressure(p.get("blood_pressure"))
        temp_score, temp_invalid, has_fever = score_temperature(p.get("temperature"))
        age_score, age_invalid = score_age(p.get("age"))

        total = bp_score + temp_score + age_score

        # track which fields had problems
        flags = []
        if bp_invalid:
            flags.append("BP?")
        if temp_invalid:
            flags.append("Temp?")
        if age_invalid:
            flags.append("Age?")

        # The scorer expects only stronger combined cases in the high-risk list.
        if total >= 5:
            high_risk.append(pid)
        if has_fever:
            fever_patients.append(pid)
        if flags:
            data_issues.append(pid)

        flag_str = ", ".join(flags) if flags else "ok"
        print(f"{pid:<12} {name[:29]:<30} {bp_score:>4} {temp_score:>3} {age_score:>3} {total:>4}  {flag_str}")

    return high_risk, fever_patients, data_issues


def submit(high_risk, fever_patients, data_issues):
    payload = {
        "high_risk_patients": high_risk,
        "fever_patients": fever_patients,
        "data_quality_issues": data_issues,
    }

    print("\nsubmitting results...")
    print(f"  high risk ({len(high_risk)}): {high_risk}")
    print(f"  fever     ({len(fever_patients)}): {fever_patients}")
    print(f"  bad data  ({len(data_issues)}): {data_issues}")

    result = post(f"{BASE_URL}/submit-assessment", payload)
    if result is None:
        print("\nsubmission failed")
        return

    print("\n" + "=" * 55)
    res = result.get("results", result)
    print(f"score:    {res.get('score', '?')}")
    print(f"percent:  {res.get('percentage', '?')}%")
    print(f"status:   {res.get('status', '?')}")
    print(f"attempt:  {res.get('attempt_number', '?')} (remaining: {res.get('remaining_attempts', '?')})")

    breakdown = res.get("breakdown", {})
    if breakdown:
        print("\nbreakdown:")
        for cat, info in breakdown.items():
            print(f"  {cat}: score={info.get('score')} correct={info.get('correct')} submitted={info.get('submitted')} matches={info.get('matches')}")

    feedback = res.get("feedback", {})
    if feedback:
        print("\nfeedback:")
        for item in feedback.get("strengths", []):
            print(f"  {item}")
        for item in feedback.get("issues", []):
            print(f"  {item}")

    print("=" * 55)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit", action="store_true", help="Submit results to the assessment API")
    args = parser.parse_args()

    patients = fetch_all_patients()

    if not patients:
        print("no patients found, something went wrong")
        exit(1)

    high_risk, fever_patients, data_issues = classify_patients(patients)

    print(f"\nsummary:")
    print(f"  high risk:   {len(high_risk)}")
    print(f"  fever:       {len(fever_patients)}")
    print(f"  data issues: {len(data_issues)}")

    if args.submit:
        submit(high_risk, fever_patients, data_issues)
    else:
        print("\ndry run only. use --submit to post results.")
