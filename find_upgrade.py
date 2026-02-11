import json
import itertools
import re
import sys

# -----------------------------
# Loading & parsing helpers
# -----------------------------

def load_unlock_conditions():
    with open("unlockConditions.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_upgrade_name_mappings():
    """
    Builds two mappings:
      real_name (lowercase) -> code_name
      code_name -> real_name
    using upgrades.ts + en.json
    """
    with open("en.json", "r", encoding="utf-8") as f:
        en = json.load(f)

    with open("upgrades.ts", "r", encoding="utf-8") as f:
        ts = f.read()

    pattern = re.compile(
        r'id:\s*"([^"]+)"[\s\S]*?name:\s*t\("([^"]+)"\)',
        re.MULTILINE,
    )

    real_to_code = {}
    code_to_real = {}

    for code_id, translation_key in pattern.findall(ts):
        real_name = en.get(translation_key)
        if real_name:
            real_to_code[real_name.lower()] = code_id
            code_to_real[code_id] = real_name

    return real_to_code, code_to_real


# -----------------------------
# Normalization
# -----------------------------

def normalize_real_names(names, real_to_code):
    result = set()
    for name in names:
        key = name.strip().lower()
        if not key:
            continue
        if key not in real_to_code:
            print(f"⚠️  Unknown upgrade: '{name.strip()}'")
            continue
        result.add(real_to_code[key])
    return result


def pretty_upgrades(code_names, code_to_real):
    return [code_to_real.get(c, c) for c in code_names]


# -----------------------------
# Evaluation logic
# -----------------------------

def evaluate_combo(combo, already_chosen, levels):
    full_set = already_chosen | set(combo)
    unlocked = []
    almost = []

    for level_name, data in levels.items():
        required = set(data.get("required", []))
        forbidden = set(data.get("forbidden", []))

        if full_set & forbidden:
            continue

        missing = required - full_set
        if not missing:
            unlocked.append(level_name)
        else:
            almost.append((level_name, len(missing), missing))

    almost.sort(key=lambda x: x[1])
    return unlocked, almost


def recommend_upgrades(chosen, available, max_picks, levels):
    best_unlocks = -1
    best_almost_score = float("inf")
    best_combo_size = float("inf")
    best_results = []

    for r in range(1, max_picks + 1):
        for combo in itertools.combinations(available, r):
            unlocked, almost = evaluate_combo(combo, chosen, levels)

            unlock_count = len(unlocked)
            closest_missing = almost[0][1] if almost else float("inf")

            is_better = False

            if unlock_count > best_unlocks:
                is_better = True
            elif unlock_count == best_unlocks:
                if unlock_count > 0:
                    # Prefer fewer upgrades if same unlock count
                    if r < best_combo_size:
                        is_better = True
                else:
                    # No immediate unlocks → closer to unlocking
                    if closest_missing < best_almost_score:
                        is_better = True
                    elif closest_missing == best_almost_score and r < best_combo_size:
                        is_better = True

            if is_better:
                best_unlocks = unlock_count
                best_almost_score = closest_missing
                best_combo_size = r
                best_results = [(combo, unlocked, almost)]
            elif (
                unlock_count == best_unlocks
                and closest_missing == best_almost_score
                and r == best_combo_size
            ):
                best_results.append((combo, unlocked, almost))

    return best_results

def prompt_for_upgrades(prompt, real_to_code):
    """
    Prompts until all entered upgrade names are valid.
    Returns a set of code names.
    """
    while True:
        raw = input(prompt).strip()
        if not raw:
            return set()

        names = [n.strip() for n in raw.split(",") if n.strip()]
        unknown = [
            n for n in names
            if n.lower() not in real_to_code
        ]

        if unknown:
            print(
                f"❌ Unknown upgrade(s): {', '.join(unknown)}"
            )
            print("Please re-enter the full list.\n")
            continue

        return {real_to_code[n.lower()] for n in names}




# -----------------------------
# Main loop
# -----------------------------

def main():
    try:
        levels = load_unlock_conditions()
        real_to_code, code_to_real = load_upgrade_name_mappings()
    except FileNotFoundError as e:
        print(f"Missing required file: {e.filename}")
        sys.exit(1)

    level_number = 1
    chosen_upgrades = set()

    print("\n=== Upgrade Optimizer ===")
    print("Press Ctrl+C to quit.\n")

    while True:
        print(f"\n=== GAME LEVEL {level_number} ===")

        if level_number == 1:
            chosen_upgrades |= prompt_for_upgrades(
                "Current upgrades: ", real_to_code
            )

        available_upgrades = prompt_for_upgrades(
            "Available upgrades: ", real_to_code
        )



        try:
            pick_count = int(
                input("How many upgrades can you choose? ").strip()
            )
        except ValueError:
            print("Invalid number.")
            continue

        results = recommend_upgrades(
            chosen_upgrades, available_upgrades, pick_count, levels
        )

        print("\n=== RECOMMENDATIONS ===\n")

        for combo, unlocked, almost in results:
            print("Recommended upgrades:")
            for name in pretty_upgrades(combo, code_to_real):
                print(f"  - {name}")

            if unlocked:
                print("\nUnlocked now:")
                for lvl in unlocked:
                    print(f"  ✔ {lvl}")
            else:
                print("\nUnlocked now: None")

            if almost:
                print("\nAlmost unlocked:")
                for lvl, _, missing in almost[:10]:
                    missing_pretty = pretty_upgrades(missing, code_to_real)
                    print(
                        f"  • {lvl} (missing: {', '.join(missing_pretty)})"
                    )

            print("-" * 50)

        chosen_upgrades |= prompt_for_upgrades(
            "\nWhich upgrades did you choose? ", real_to_code
        )


        level_number += 1


if __name__ == "__main__":
    main()
