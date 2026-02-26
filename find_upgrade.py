import json
import itertools
import re
import sys

TOP_K = 5

def paginate_options(options, render_fn):
    i = 0
    n = len(options)

    while i < n:
        chunk = options[i:i+TOP_K]

        for opt in chunk:
            render_fn(opt)

        i += TOP_K

        if i >= n:
            break

        ans = input(
            "\nType 'more' to see additional options or press Enter to continue: "
        ).strip().lower()

        if ans != "more":
            break

def paginate_details(results, code_to_real, code_to_category):
    i = 0
    n = len(results)

    while i < n:
        chunk = results[i:i+TOP_K]

        for combo, missing, *_ in chunk:
            print("\nFor combo:", ", ".join(code_to_real[u] for u in combo))
            show_details(combo, missing, code_to_real, code_to_category)

        i += TOP_K

        if i >= n:
            break

        ans = input(
            "\nType 'more' to see 5 more or press Enter to continue: "
        ).strip().lower()

        if ans != "more":
            break

def render_unlock_option(opt, code_to_real):
    combo, unlocked, missing = opt

    print("Recommended upgrades:")
    for u in combo:
        print("  -", code_to_real[u])

    print("\nUnlocks:", len(unlocked))
    for l in unlocked:
        print("  ✔", l)

    counts = off_by_counts(missing)
    print()
    print_off_by_totals(counts)

    print("-" * 40)

def render_almost_option(opt, code_to_real):
    combo, missing, counts, off1 = opt

    print("Recommended upgrades:")
    for u in combo:
        print("  -", code_to_real[u])

    print()
    print_off_by_totals(counts)

    print("-" * 40)

# -------------------------------------------------
# Load files
# -------------------------------------------------

def load_unlock_conditions():
    with open("unlockConditions.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_upgrade_data():
    """
    Returns:
      real_to_code
      code_to_real
      code_to_category
    """
    with open("en.json", "r", encoding="utf-8") as f:
        en = json.load(f)

    with open("upgrades.ts", "r", encoding="utf-8") as f:
        ts = f.read()

    pattern = re.compile(
        r'category:\s*categories\.(\w+)[\s\S]*?id:\s*"([^"]+)"[\s\S]*?name:\s*t\("([^"]+)"\)',
        re.MULTILINE,
    )

    real_to_code = {}
    code_to_real = {}
    code_to_category = {}

    for category, code_id, tkey in pattern.findall(ts):
        real_name = en.get(tkey)
        if real_name:
            real_to_code[real_name.lower()] = code_id
            code_to_real[code_id] = real_name
            code_to_category[code_id] = category

    return real_to_code, code_to_real, code_to_category


# -------------------------------------------------
# Input validation
# -------------------------------------------------

def prompt_for_upgrades(prompt, real_to_code):
    while True:
        raw = input(prompt).strip()
        if not raw:
            return set()

        names = [n.strip() for n in raw.split(",") if n.strip()]
        unknown = [n for n in names if n.lower() not in real_to_code]

        if unknown:
            print(f"❌ Unknown upgrade(s): {', '.join(unknown)}")
            print("Please re-enter the full list.\n")
            continue

        return {real_to_code[n.lower()] for n in names}


# -------------------------------------------------
# Evaluation helpers
# -------------------------------------------------

def evaluate_levels(combo, chosen, levels):
    full = chosen | set(combo)

    unlocked = []
    missing_map = {}

    for lvl, data in levels.items():
        req = set(data.get("required", []))
        forb = set(data.get("forbidden", []))

        if full & forb:
            continue

        missing = req - full
        if not missing:
            unlocked.append(lvl)
        else:
            missing_map[lvl] = missing

    return unlocked, missing_map


def off_by_counts(missing_map):
    counts = {}
    for m in missing_map.values():
        n = len(m)
        counts[n] = counts.get(n, 0) + 1
    return counts

def print_off_by_totals(counts):
    if not counts:
        print("Off-by-1: 0")
        return

    max_k = max(counts.keys())

    for k in range(1, max_k + 1):
        print(f"Off-by-{k}: {counts.get(k, 0)}")


# -------------------------------------------------
# Recommendation engine (new rules)
# -------------------------------------------------

def recommend(chosen, available, max_picks, levels, code_to_category):
    """
    Returns:
      mode = "unlock" or "almost"
      results = list of tuples compatible with existing renderers

    Rules implemented:
      1. Immediate unlocks first
      2. If none → off-1 non-combo
      3. If none → maximize off-2, off-3...
      4. Non-combo only in almost mode
      5. If combo doesn't change totals → show baseline totals
      6. Always return recommendations if any non-combo available
    """

    # -------------------------------------------------
    # Baseline totals (no new upgrades)
    # -------------------------------------------------
    _, baseline_missing = evaluate_levels((), chosen, levels)
    baseline_counts = off_by_counts(baseline_missing)

    # -------------------------------------------------
    # PASS 1 — IMMEDIATE UNLOCKS (combo allowed)
    # -------------------------------------------------
    best_unlock = 0
    unlock_sets = []

    for r in range(1, max_picks + 1):
        for combo in itertools.combinations(available, r):
            unlocked, missing = evaluate_levels(combo, chosen, levels)

            ucount = len(unlocked)

            if ucount > best_unlock:
                best_unlock = ucount
                unlock_sets = [(combo, unlocked, missing)]
            elif ucount == best_unlock and ucount > 0:
                unlock_sets.append((combo, unlocked, missing))

    if best_unlock > 0:
        ranked = []
        for combo, unlocked, missing in unlock_sets:
            off1 = sum(1 for m in missing.values() if len(m) == 1)
            ranked.append((combo, unlocked, missing, off1))

        ranked.sort(key=lambda x: x[3], reverse=True)

        # renderer expects (combo, unlocked, missing)
        return "unlock", [(c, u, m) for c, u, m, _ in ranked]

    # -------------------------------------------------
    # PASS 2 — ALMOST MODE (NON-COMBO ONLY)
    # -------------------------------------------------
    candidates = []

    for r in range(1, max_picks + 1):
        for combo in itertools.combinations(available, r):

            # non-combo restriction
            if any(code_to_category.get(u) == "combo" for u in combo):
                continue

            unlocked, missing = evaluate_levels(combo, chosen, levels)
            counts = off_by_counts(missing)

            # preserve baseline if unchanged or empty
            if not counts or counts == baseline_counts:
                counts = baseline_counts

            candidates.append((combo, missing, counts))

    if not candidates:
        return "almost", []

    # -------------------------------------------------
    # CHECK OFF-1 EXISTENCE
    # -------------------------------------------------
    max_off1 = max(c[2].get(1, 0) for c in candidates)

    if max_off1 > 0:
        ranked = [
            (combo, missing, counts, counts.get(1, 0))
            for combo, missing, counts in candidates
        ]

        ranked.sort(key=lambda x: x[3], reverse=True)
        return "almost", ranked

    # -------------------------------------------------
    # FALLBACK — MAXIMIZE OFF-2, OFF-3, ...
    # -------------------------------------------------
    def rank_tuple(counts):
        if not counts:
            return (0,)
        max_k = max(counts.keys())
        return tuple(counts.get(k, 0) for k in range(2, max_k + 1))

    ranked = [
        (combo, missing, counts, rank_tuple(counts))
        for combo, missing, counts in candidates
    ]

    ranked.sort(key=lambda x: x[3], reverse=True)
    return "almost", ranked

# -------------------------------------------------
# Detail display
# -------------------------------------------------

def show_details(combo, missing, code_to_real, code_to_category):
    print("\n=== LEVEL DETAILS ===\n")

    # sort levels by number of missing upgrades
    sorted_levels = sorted(
        missing.items(),
        key=lambda item: len(item[1])
    )

    for lvl, miss in sorted_levels:
        names = []
        for u in miss:
            name = code_to_real.get(u, u)
            if code_to_category.get(u) != "combo":
                name = f"*{name}*"  # highlight non-combo
            names.append(name)

        print(f"{lvl}: missing {', '.join(names)}")

    print("\n(* non-combo upgrades)\n")


# -------------------------------------------------
# Main loop
# -------------------------------------------------

def main():
    try:
        levels = load_unlock_conditions()
        real_to_code, code_to_real, code_to_category = load_upgrade_data()
    except FileNotFoundError as e:
        print(f"Missing file: {e.filename}")
        sys.exit(1)

    chosen = set()
    level_num = 1

    print("\n=== Upgrade Optimizer ===")
    print("Press Ctrl+C to exit.\n")

    while True:
        print(f"\n=== GAME LEVEL {level_num} ===")

        if level_num == 1:
            chosen |= prompt_for_upgrades("Current upgrades: ", real_to_code)

        available = prompt_for_upgrades("Available upgrades: ", real_to_code)

        while True:
            try:
                max_picks = int(input("How many upgrades can you choose? "))
                break
            except:
                print("Invalid number.")

        mode, results = recommend(
            chosen, available, max_picks, levels, code_to_category
        )

        print("\n=== RECOMMENDATIONS ===\n")

        # ---------- immediate unlock mode ----------
        if mode == "unlock":
            paginate_options(
                results,
                lambda opt: render_unlock_option(opt, code_to_real)
            )

            ans = input(
                "\nType 'details' to see level requirements or press Enter to continue: "
            ).strip().lower()

            if ans == "details":
                paginate_details(results, code_to_real, code_to_category)

        # ---------- off-by-one mode ----------
        else:
            paginate_options(
                results,
                lambda opt: render_almost_option(opt, code_to_real)
            )

            ans = input(
                "\nType 'details' to see level requirements or press Enter to continue: "
            ).strip().lower()

            if ans == "details":
                paginate_details(results, code_to_real, code_to_category)

        chosen |= prompt_for_upgrades("\nWhich upgrades did you choose? ", real_to_code)

        level_num += 1


if __name__ == "__main__":
    main()