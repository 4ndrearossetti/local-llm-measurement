#!/usr/bin/env python3
"""
Summarise the CSV produced by decompose.py.

Prints:
  1. Per session: request count, peak size, final composition as % of peak,
     number of compactions and aux requests.
  2. Overall composition shares across all conversation states, and per model.
  3. Compaction table: for each compaction, size before (last true
     conversation state) and after, total drop, and the share of each role in
     what was dropped. Negative per-role changes (a role that grew during
     compaction) are shown as 0 in the drop shares.
  4. Post-compaction regrowth: for each compaction, how many characters of
     tool results reappeared within the next three conversation states —
     the measured cost of dropping reconstructible content.

Aux requests (event=aux_request, e.g. the client's own summarisation calls)
are excluded from composition statistics and from the state chain; they are
counted per session so their presence is visible.
"""

import csv
import sys
from collections import defaultdict

ROLES = ['system', 'user', 'assistant', 'tool', 'toolschema']


def load(path):
    with open(path, newline='') as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ('req_idx', 'session_id', 'n_messages', 'total_chars',
                  'system_chars', 'user_chars', 'assistant_chars',
                  'tool_chars', 'toolschema_chars', 'delta_chars_vs_prev'):
            r[k] = int(r[k])
    return rows


def role_chars(row):
    return {role: row[f'{role}_chars'] for role in ROLES}


def pct(part, whole):
    return 100.0 * part / whole if whole else 0.0


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <output.csv>", file=sys.stderr)
        sys.exit(1)

    rows = load(sys.argv[1])
    states = [r for r in rows if r['event'] != 'aux_request']

    sep = "=" * 80

    # ---- 1. Per session ---------------------------------------------------
    print(sep)
    print("PER SESSION")
    print(sep)

    sessions = defaultdict(list)
    for r in rows:
        sessions[r['session_id']].append(r)

    for sid in sorted(sessions):
        srows = sessions[sid]
        sstates = [r for r in srows if r['event'] != 'aux_request']
        if not sstates:
            continue
        peak = max(r['total_chars'] for r in sstates)
        final = sstates[-1]
        n_comp = sum(1 for r in srows if r['event'] == 'compaction')
        n_aux = sum(1 for r in srows if r['event'] == 'aux_request')
        files = sorted({r['file'] for r in srows})
        models = sorted({r['model'] for r in sstates})

        print(f"\nSession {sid}  [{', '.join(files)}]  model: {', '.join(models)}")
        print(f"  Requests:          {len(sstates)} states"
              + (f" + {n_aux} aux" if n_aux else ""))
        print(f"  Peak total_chars:  {peak:,}")
        print(f"  Compactions:       {n_comp}")
        print(f"  Final composition (% of peak):")
        fc = role_chars(final)
        for role in ROLES:
            print(f"    {role + ':':<12} {pct(fc[role], peak):5.1f}%")

    # ---- 2. Overall composition ------------------------------------------
    print()
    print(sep)
    print("OVERALL COMPOSITION SHARES (conversation states only)")
    print(sep)

    def composition(rs):
        totals = {role: sum(r[f'{role}_chars'] for r in rs) for role in ROLES}
        grand = sum(totals.values())
        return totals, grand

    totals, grand = composition(states)
    print(f"\nAcross all {len(states)} conversation states "
          f"({len(rows) - len(states)} aux requests excluded):")
    for role in ROLES:
        print(f"  {role + ':':<12} {pct(totals[role], grand):5.1f}%")

    by_model = defaultdict(list)
    for r in states:
        by_model[r['model']].append(r)

    print("\nPer model:")
    for model in sorted(by_model):
        mt, mg = composition(by_model[model])
        print(f"  {model}:")
        for role in ROLES:
            print(f"    {role + ':':<12} {pct(mt[role], mg):5.1f}%")

    # ---- 3. Compaction table ----------------------------------------------
    print()
    print(sep)
    print("COMPACTIONS")
    print(sep)

    # Reconstruct before/after against the last true conversation state,
    # walking rows in file order per the CSV.
    comp_events = []  # (session, req_idx, before_row, after_row)
    prev_state = None
    for r in rows:
        if r['event'] == 'aux_request':
            continue
        if r['event'] == 'compaction' and prev_state is not None:
            comp_events.append((r['session_id'], r['req_idx'], prev_state, r))
        prev_state = r

    if not comp_events:
        print("\n(none detected)")
    else:
        hdr = (f"\n{'Sess':<6}{'Req':<6}{'Before':>12}{'After':>12}{'Drop':>12}"
               + "".join(f"{('d_' + role):>13}" for role in ROLES))
        print(hdr)
        print("-" * len(hdr))
        total_before = total_after = 0
        for sid, ridx, before, after in comp_events:
            b, a = before['total_chars'], after['total_chars']
            drop = b - a
            total_before += b
            total_after += a
            bc, ac = role_chars(before), role_chars(after)
            dropped = {role: max(bc[role] - ac[role], 0) for role in ROLES}
            dropped_sum = sum(dropped.values()) or 1
            line = (f"{sid:<6}{ridx:<6}{b:>12,}{a:>12,}{drop:>12,}"
                    + "".join(f"{pct(dropped[role], dropped_sum):>12.1f}%"
                              for role in ROLES))
            print(line)

        reduced = total_before - total_after
        print(f"\nTotal characters removed by compactions: {reduced:,} "
              f"({pct(total_after, total_before):.1f}% remaining)")

    # ---- 4. Post-compaction regrowth --------------------------------------
    print()
    print(sep)
    print("POST-COMPACTION TOOL REGROWTH (within next 3 states)")
    print(sep)

    # Index conversation states in order, per session
    per_session_states = defaultdict(list)
    for r in states:
        per_session_states[r['session_id']].append(r)

    any_regrowth = False
    for sid in sorted(per_session_states):
        srows = per_session_states[sid]
        for i, r in enumerate(srows):
            if r['event'] != 'compaction':
                continue
            base_tool = r['tool_chars']
            window = srows[i + 1:i + 4]
            if not window:
                continue
            peak_tool = max(w['tool_chars'] for w in window)
            regrown = peak_tool - base_tool
            if regrown > 0:
                any_regrowth = True
                print(f"  Session {sid}, compaction at req {r['req_idx']}: "
                      f"tool chars {base_tool:,} -> {peak_tool:,} "
                      f"(+{regrown:,} re-fetched)")

    if not any_regrowth:
        print("  (no regrowth observed)")


if __name__ == '__main__':
    main()

