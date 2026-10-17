"""架空の病棟データを生成する（PLAN.md 5章）。

seed 固定なので毎回同じデータになる。出力は data/out/*.json。
最後に 5章「期待される結果」を Python 側でも検算し、崩れていたら失敗する。
"""

import json
import random
from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "out"

START = date(2026, 10, 10)
DATES = [START + timedelta(days=i) for i in range(7)]  # 10/10〜10/16

INFECTIOUS_LOOKBACK_DAYS = 2
INCUBATION_MIN_DAYS = 2
INCUBATION_MAX_DAYS = 7

WARDS = [str(n) for n in range(501, 509)]
BEDS_PER_ROOM = 4

PATIENT_IDS = [f"P{i:02d}" for i in range(1, 31)]
PATIENT_NAMES = [
    "Sato", "Suzuki", "Takahashi", "Watanabe", "Ito", "Yamamoto",
    "Nakamura", "Kobayashi", "Kato", "Yoshida", "Yamada", "Tanaka",
    "Sasaki", "Yamaguchi", "Matsumoto", "Inoue", "Kimura", "Hayashi",
    "Shimizu", "Yamazaki", "Ikeda", "Hashimoto", "Abe", "Ishikawa",
    "Ogawa", "Fujita", "Okada", "Goto", "Hasegawa", "Murakami",
]

DAY_NURSES = [f"N{i:02d}" for i in range(1, 7)]     # N01〜N06 日勤
NIGHT_NURSES = [f"N{i:02d}" for i in range(7, 13)]  # N07〜N12 夜勤
DOCTORS = ["D01", "D02"]
RADIOGRAPHER = "R01"
STAFF_NAMES = {
    "N01": "Mori", "N02": "Endo", "N03": "Aoki", "N04": "Fujii",
    "N05": "Nishimura", "N06": "Fukuda", "N07": "Ota", "N08": "Miura",
    "N09": "Okamoto", "N10": "Matsuda", "N11": "Nakajima", "N12": "Harada",
    "D01": "Ono", "D02": "Takeuchi", "R01": "Kaneko",
}
# 主治医：D01 が 501〜504、D02 が 505〜508
DOCTOR_ROOMS = {"D01": WARDS[:4], "D02": WARDS[4:]}

# 仕込むシナリオ（正解）
SOURCE = "N07"  # 夜勤看護師。陽性者3人の夜勤担当。未検査
POSITIVES = {
    "P05": {"room": "501", "onset": date(2026, 10, 14), "test": date(2026, 10, 15)},
    "P12": {"room": "502", "onset": date(2026, 10, 15), "test": date(2026, 10, 16)},
    "P18": {"room": "505", "onset": date(2026, 10, 15), "test": date(2026, 10, 16)},
}
FEVER_NEGATIVES = {"P03": date(2026, 10, 14), "P22": date(2026, 10, 15)}


def hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def to_minutes(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def split_sizes(n_patients, n_nurses):
    """1勤務あたりの担当人数（4〜6人）を決める。"""
    sizes = [n_patients // n_nurses] * n_nurses
    for i in range(n_patients - sum(sizes)):
        sizes[i] += 1
    for _ in range(3):
        i, j = random.sample(range(n_nurses), 2)
        if sizes[i] < 6 and sizes[j] > 4:
            sizes[i] += 1
            sizes[j] -= 1
    return sizes


def assign_nurses(patients, nurses, fixed):
    """患者を看護師に割り振る。fixed（患者→看護師）は必ずその看護師が担当する。"""
    sizes = dict(zip(nurses, split_sizes(len(patients), len(nurses))))
    groups = {n: [] for n in nurses}
    for p, n in fixed.items():
        groups[n].append(p)
    rest = [p for p in patients if p not in fixed]
    random.shuffle(rest)
    for n in nurses:
        while len(groups[n]) < sizes[n]:
            groups[n].append(rest.pop())
    assert not rest
    return groups


def build():
    random.seed(42)

    # --- 部屋 ---
    rooms = [{"id": r, "name": f"Room {r}", "type": "ward"} for r in WARDS]
    rooms += [
        {"id": "XRAY", "name": "X-ray room", "type": "xray"},
        {"id": "LAB", "name": "Lab", "type": "lab"},
        {"id": "STATION", "name": "Nurse station", "type": "station"},
    ]

    # --- 病室の割り当て（陽性者3人は別々の部屋に固定）---
    slots = [r for r in WARDS for _ in range(BEDS_PER_ROOM)]
    for info in POSITIVES.values():
        slots.remove(info["room"])
    random.shuffle(slots)
    others = [p for p in PATIENT_IDS if p not in POSITIVES]
    room_of = {p: info["room"] for p, info in POSITIVES.items()}
    room_of.update(zip(others, slots))

    # --- 患者 ---
    patients = []
    for pid, name in zip(PATIENT_IDS, PATIENT_NAMES):
        patients.append({
            "id": pid,
            "name": name,
            "age": random.randint(45, 92),
            "sex": random.choice("MF"),
            "admitted_date": START - timedelta(days=random.randint(1, 14)),
            "room_id": room_of[pid],
            "status": "untested",
            "test_date": None,
            "onset_date": None,
            "isolated_date": None,
            "fever_date": None,
        })
    by_id = {p["id"]: p for p in patients}

    for pid, info in POSITIVES.items():
        by_id[pid].update(status="positive", onset_date=info["onset"],
                          test_date=info["test"], isolated_date=info["test"])
    for pid, fever in FEVER_NEGATIVES.items():
        by_id[pid].update(status="fever_negative", fever_date=fever, test_date=fever)
    # 陽性者の同室者は、陽性判明日にスクリーニング検査で陰性
    for pid, info in POSITIVES.items():
        for p in patients:
            if p["room_id"] == info["room"] and p["status"] == "untested":
                p.update(status="negative", test_date=info["test"])

    # --- 入院（途中入退院なし。全員が7日間同じ病室）---
    stays = [{"patient_id": p["id"], "room_id": p["room_id"], "date": d}
             for d in DATES for p in patients]

    # --- 看護師の担当 ---
    # 日勤：陽性者3人はそれぞれ別の日勤看護師が受け持ち（共通の日勤看護師を作らない）
    day_primary = dict(zip(POSITIVES, random.sample(DAY_NURSES, len(POSITIVES))))
    # 夜勤：陽性者3人とも N07 が受け持ち
    night_primary = {pid: SOURCE for pid in POSITIVES}

    cares = []
    for d in DATES:
        for shift, nurses, fixed in (("day", DAY_NURSES, day_primary),
                                     ("night", NIGHT_NURSES, night_primary)):
            for nurse, group in assign_nurses(PATIENT_IDS, nurses, fixed).items():
                for pid in sorted(group):
                    cares.append({"staff_id": nurse, "patient_id": pid,
                                  "date": d, "shift": shift})

    # --- 医師の担当（日勤）---
    # 平常時は陽性者以外の担当患者から2〜3人。症状が出た患者（発症日以降の陽性者、
    # 発熱日の発熱陰性者）は追加で診る。潜伏期間内に陽性者2人を診る医師は出ない。
    for d in DATES:
        for doctor, doc_rooms in DOCTOR_ROOMS.items():
            mine = [p for p in patients if p["room_id"] in doc_rooms]
            routine = [p["id"] for p in mine if p["id"] not in POSITIVES]
            seen = set(random.sample(routine, random.randint(2, 3)))
            for p in mine:
                if p["id"] in POSITIVES and d >= p["onset_date"]:
                    seen.add(p["id"])
                if p["fever_date"] == d:
                    seen.add(p["id"])
            for pid in sorted(seen):
                cares.append({"staff_id": doctor, "patient_id": pid,
                              "date": d, "shift": "day"})

    # --- 検査室・X線室（患者の約1/3が1回）---
    visits = [
        # 陽性者は発症後にX線。潜伏期間の外で、互いに時間も重ならない
        {"patient_id": "P05", "room_id": "XRAY", "date": date(2026, 10, 14), "start": "10:00", "end": "10:20"},
        {"patient_id": "P12", "room_id": "XRAY", "date": date(2026, 10, 15), "start": "09:30", "end": "09:50"},
        {"patient_id": "P18", "room_id": "XRAY", "date": date(2026, 10, 15), "start": "13:30", "end": "13:50"},
    ]
    # 発熱陰性者は発熱日に検査
    for pid, room in (("P03", "XRAY"), ("P22", "LAB")):
        start = random.randrange(9 * 60, 12 * 60, 10)
        visits.append({"patient_id": pid, "room_id": room, "date": FEVER_NEGATIVES[pid],
                       "start": hhmm(start), "end": hhmm(start + random.randrange(15, 41, 5))})
    pool = [p for p in PATIENT_IDS if p not in POSITIVES and p not in FEVER_NEGATIVES]
    for pid in sorted(random.sample(pool, 5)):
        start = random.randrange(9 * 60, 11 * 60 + 30, 10)
        visits.append({"patient_id": pid, "room_id": random.choice(["XRAY", "LAB"]),
                       "date": random.choice(DATES), "start": hhmm(start),
                       "end": hhmm(start + random.randrange(15, 41, 5))})
    # 放射線技師は X線の患者を担当
    for v in visits:
        if v["room_id"] == "XRAY":
            cares.append({"staff_id": RADIOGRAPHER, "patient_id": v["patient_id"],
                          "date": v["date"], "shift": "day"})

    # --- スタッフ ---
    staff = []
    for sid, name in STAFF_NAMES.items():
        role = {"N": "nurse", "D": "doctor", "R": "radiographer"}[sid[0]]
        staff.append({"id": sid, "name": name, "role": role, "status": "untested",
                      "test_date": None, "onset_date": None, "isolated_date": None})
    # 陽性者の日勤受け持ち看護師は 10/16 に検査して陰性。夜勤の N07 は未検査のまま
    for s in staff:
        if s["id"] in day_primary.values():
            s.update(status="negative", test_date=date(2026, 10, 16))

    # --- 勤務（ナースステーション）---
    shifts = []
    for d in DATES:
        for sid in DAY_NURSES + DOCTORS + [RADIOGRAPHER]:
            shifts.append({"staff_id": sid, "room_id": "STATION", "date": d, "shift": "day"})
        for sid in NIGHT_NURSES:
            shifts.append({"staff_id": sid, "room_id": "STATION", "date": d, "shift": "night"})

    return {
        "patients": patients, "staff": staff, "rooms": rooms, "stays": stays,
        "cares": cares, "visits": visits, "shifts": shifts,
    }


# ---------------------------------------------------------------------------
# 検算（load.py の CONTACT 導出と 7-1・7-2 の Cypher を Python でなぞる）
# ---------------------------------------------------------------------------

def close_contacts(data):
    contacts = []  # (person_a, person_b, date)
    room_day = defaultdict(list)
    for s in data["stays"]:
        room_day[(s["room_id"], s["date"])].append(s["patient_id"])
    for (_, d), ps in room_day.items():
        contacts += [(a, b, d) for a, b in combinations(ps, 2)]
    contacts += [(c["staff_id"], c["patient_id"], c["date"]) for c in data["cares"]]
    visit_day = defaultdict(list)
    for v in data["visits"]:
        visit_day[(v["room_id"], v["date"])].append(v)
    for (_, d), vs in visit_day.items():
        for v1, v2 in combinations(vs, 2):
            overlap = (min(to_minutes(v1["end"]), to_minutes(v2["end"]))
                       - max(to_minutes(v1["start"]), to_minutes(v2["start"])))
            if overlap >= 15:
                contacts.append((v1["patient_id"], v2["patient_id"], d))
    return contacts


def source_candidates(data, contacts):
    windows = {}
    for p in data["patients"] + data["staff"]:
        if p["status"] == "positive":
            ref = p["onset_date"] or p["test_date"]
            windows[p["id"]] = (ref - timedelta(days=INCUBATION_MAX_DAYS),
                                ref - timedelta(days=INCUBATION_MIN_DAYS))
    linked = defaultdict(set)
    for a, b, d in contacts:
        for pos, x in ((a, b), (b, a)):
            if pos in windows and windows[pos][0] <= d <= windows[pos][1]:
                linked[x].add(pos)
    return {x: ps for x, ps in linked.items() if len(ps) >= 2}


def first_gen(data, contacts, index_id):
    p = next(p for p in data["patients"] if p["id"] == index_id)
    ws = (p["onset_date"] or p["test_date"]) - timedelta(days=INFECTIOUS_LOOKBACK_DAYS)
    we = p["isolated_date"] or date(2099, 12, 31)
    out = set()
    for a, b, d in contacts:
        if ws <= d <= we and index_id in (a, b):
            out.add(b if a == index_id else a)
    return out


def check(data):
    contacts = close_contacts(data)
    candidates = source_candidates(data, contacts)
    assert candidates == {SOURCE: set(POSITIVES)}, f"source candidates: {candidates}"
    roommates = {p["id"] for p in data["patients"]
                 if p["room_id"] == POSITIVES["P12"]["room"] and p["id"] != "P12"}
    gen1 = first_gen(data, contacts, "P12")
    assert SOURCE in gen1 and roommates <= gen1, f"P12 first gen: {sorted(gen1)}"
    return candidates, gen1


def main():
    data = build()
    candidates, gen1 = check(data)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in data.items():
        with open(OUT_DIR / f"{name}.json", "w") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1, default=str)
    print(f"wrote {OUT_DIR}: " + ", ".join(f"{k}={len(v)}" for k, v in data.items()))
    for x, ps in candidates.items():
        print(f"source candidate: {x} linked to {sorted(ps)}")
    print(f"P12 first gen: {sorted(gen1)}")


if __name__ == "__main__":
    main()
