---
description: Agent Trading Desk publish run — builds the public tree from this private one, runs both leak gates, and stages a commit in the public repo. Shows the human exactly what would reach GitHub, waits for their explicit yes, and only then pushes. Halts on the first gate failure.
---


You are the **publisher**. You turn this private tree into the public one, show
the human exactly what would reach GitHub, and push only once they have said yes.

Publishing is a one-way door: git history is permanent. What ships is the
method, plus a track record in counts and percentages — never a position size,
a cash figure or the working papers behind them. A leak that reaches GitHub
cannot be fixed by a later commit. So this contract is deliberately gate-heavy,
and its last step is guarded by a human decision rather than by a rule you keep
for them.

**Until 2026-08-25 this command never pushed at all** — it stopped at a staged
commit and the human ran `git push` themselves. That was changed by the owner,
deliberately, after the rule was waived in practice: a gate that gets talked
past without being rewritten is worse than no gate, because it teaches everyone
that the written contract is not the real one. The protection it provided is
kept in step 8, which is now the only interactive step in the repo.

**Run steps 1–7 in order without asking the human anything.** Stop only where a
HALT is specified, and when you stop, say which step stopped you and what the
human has to do. **Step 8 is the one deliberate exception** — it asks, and it
waits.

Let `<dst>` be the destination tree. Default `~/trading-portfolio-public`; if
`$ARGUMENTS` names a path, use that instead.

Let `<remote>` be the public repo's HTTPS URL. Resolve it in this order:

1. `git -C <dst> remote get-url origin` if `<dst>/.git` already exists — an
   established repo names its own remote and you must not second-guess it.
2. Otherwise `$ARGUMENTS` if it looks like `owner/repo` or a GitHub URL.
3. Otherwise the configured default:
   **`https://github.com/sensei-51/agent-trading-desk.git`**

Never invent an owner or a repo name, and never guess one from the directory
name. If all three fail to produce a remote, **HALT** and ask — pushing a
portfolio to the wrong account is not recoverable.

---

## 1 — Preflight: confirm this is the private tree

```bash
test -d providers/private && test -f tools/publish.py && echo "PRIVATE TREE OK"
```

If that prints nothing, you are in the wrong directory — **HALT**. Every step
below assumes the source is the private tree.

Then confirm a git identity exists, because a commit without one fails at the
worst moment (after the gates have passed):

```bash
git config --get user.name && git config --get user.email
```

If either is empty, **HALT** and tell the human to set them — and mention that
a `@users.noreply.github.com` address keeps their real email out of a permanent
public history. Do not set them yourself; an identity is the human's to choose.

## 2 — Refresh the track record

**In the private tree**, because it is the only place the real ledger exists:

```bash
python3 tools/scorecard.py
```

This rebuilds the `Track record` block in `README.md` from
`output/ledger/Gate_Ledger.csv` and emits **counts and percentages only** — no
quantity, no cash figure, no sleeve NAV. It is the public evidence that replaced
publishing `output/` wholesale, and it is the only artefact in this run that
carries the real book's shape.

The script guards its own output and exits non-zero rather than writing a
currency figure or a quantity. If that guard trips, **HALT and quote it** — do
not hand-edit the block to get past it. The guard failing means the generator
started emitting sizes, and the generator is what the boundary rests on.

Needs network to price blocked ideas. `--offline` still scores closed trades and
is fine when the network is unavailable; say which mode you used.

## 3 — Dry run: read what is held back

```bash
python3 tools/publish.py --to <dst> --dry-run
```

Print the excluded paths. Confirm the two load-bearing exclusions are among
them — `providers/private/` and `input/capture/`. If either is missing from the
exclusion list, **HALT**: the structural boundary is not doing its job, and no
amount of downstream checking substitutes for it.

## 4 — Clear stale files from an established public tree

**Only if `<dst>/.git` already exists.** Skip entirely on a first publish.

`publish.py` copies into the destination; it never deletes from it. So a file
you deleted here stays in the public repo forever unless it is cleared first —
a silent way for a retired rule or an old evaluation to keep living in public.

```bash
find <dst> -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
```

This is safe **only** because everything in `<dst>` except `.git` is generated
and about to be rebuilt from scratch by step 5. Never run it against a tree that
holds hand-written work, and never against this private tree.

## 5 — Build the public tree

```bash
python3 tools/publish.py --to <dst> --force
```

`publish.py` is an **allow-list**: nothing ships unless a pattern in its `ALLOW`
list names it. A file created since the last publish is private by default, so
the failure mode is a missing file in the public repo — visible and fixable —
rather than a leaked one, which is neither.

**Never pass `--regen`.** It rebuilds `output/` *inside* the published tree
after the copy, which is the one path that bypasses the allow-list entirely.
Intermediates are not size-free and are not published; the README track record
from step 2 is the evidence.

Then it asserts its own post-conditions, including the **vendor sweep** — no
allow-listed file may name a private provider. A failure there is a real leak of
which paid service you subscribe to, and it is a HALT like any other. Do not
resolve it by deleting the file from `<dst>`: either genericise the name in the
private tree, or drop the file from `ALLOW`.

- **Exit 0** → continue.
- **Non-zero** → the post-conditions failed. Read them out verbatim and **HALT**.
  A failed post-condition means something private reached the destination tree.
  Do not "fix" it by deleting the offending file from `<dst>` and re-running the
  gate — find why `publish.py` copied it, and fix that.

An empty `output/` in the published tree is **correct**, not a defect. The
audit claim is carried by the README track record, which is generated from the
same ledger and cannot disclose a size.

## 6 — The leak sweep, over the published tree

```bash
python3 tools/checks.py --publish --tree <dst>
```

**From the private tree, pointed at `<dst>`.** This is the opposite of the rule
that stood here until 2026-09-01, and the change is the point. The sweep needs
both books at once — the private one to know what the real figures are, the
published one to prove they are absent — and the old invocation (`cd <dst> &&
checks.py --publish`) gave it only the published one. There it found the demo
book, had no needle to search for, and returned `⚪ SKIP` on every publish this
repo has ever done. The gate this step leans on had never once fired. Running it
in the private tree without `--tree` is still wrong and still refused; `--tree`
is what makes the private tree the right place to stand.

Two gates run: no provider declaring `private: True` exists in `<dst>`, and no
real figure from the private book appears anywhere in it. The needles are the
NAV, every historical NAV, the 5% line caps and **every position value in the
broker CSVs** — the 2026-09-01 leak was a single cash line, not the NAV, so a
sweep that knew only totals would have walked past it.

Any `⛔ FAIL` → **HALT** and quote it. A hit means a size reached the published
tree. Fix the source in the private tree and re-publish; never delete the file
from `<dst>` to clear the gate. Expect a line naming how many figures were swept
— `⚪ SKIP` here now means the check could not run, not that it passed, and is
itself worth stopping on.

## 7 — Stage the commit

First publish only — initialise and wire the remote:

```bash
git -C <dst> init -b main
git -C <dst> remote add origin <remote>
```

Then, every time:

```bash
git -C <dst> add -A
git -C <dst> status --short
```

Print that status in full. It is the human's last look at the actual file list
before anything becomes permanent, so do not summarise it, truncate it, or
describe it in prose. If it lists anything under `output/`, any broker CSV, any
watchlist, or anything under `providers/private/`, **HALT** — the allow-list
should have made every one of those impossible, so a sighting means the boundary
itself is broken.

`input/tracking/universe.example.md` and `input/tracking/sector_map.md` **do**
ship and are not a halt, but they get there by different routes.
`universe.example.md` is a starter list written for this purpose, copied as-is.

`sector_map.md` is **generated** (2026-09-01), not copied — it left the allow-list
the day it was noticed that shipping it whole publishes the roster. Every held name
must be classified there or `check_held_classified` fails, so the file tracks the
book by construction; and its Note column is free text, which on 27 Aug 2026 came
to read "added 27 Aug 2026 when CMX1 entered the book" — a position and its entry
date, in a file no gate reads for prose. `write_public_sector_map()` now derives
the published copy: the ticker table filtered to the demo book and starter list,
the Investable line column set to `none` throughout, and the header authored by the
generator so private free text cannot reach it by default. Step 5 prints how many
mappings were kept and how many withheld — a sudden jump in *kept* is worth a look,
because it means the demo book or the starter list grew.

The real `input/tracking/universe.md` **stopped shipping on 2026-08-25**, as did
`sector-coverage.md`. Seeing either in the file list is therefore a HALT now, where
until that date it was expected. The universe had been generalised in Aug 2026 so it
*could* ship — vendor scores scrubbed, sources reduced to "YouTube / news article" —
but that only made it publishable, never worth publishing: it still records what its
owner is researching and when each idea arrived.

Commit with a message naming the run date:

```bash
git -C <dst> commit -m "Publish <date>"
```

## 8 — Show the human, wait for a yes, then push

A push is permanent and public. This step exists so that it happens because the
human looked and agreed, never because the run had momentum.

**Show them, in this order, and do not summarise any of it:**

1. The **full** `git status --short` from step 7 — every path, untruncated. If it
   is long, show it long.
2. `git -C <dst> log --oneline origin/main..HEAD` — the commits that would land.
3. `git -C <dst> diff --stat origin/main..HEAD` — the shape of the change.
4. One plain sentence naming anything a reader would newly learn about the book:
   a ticker named for the first time, a rule that changed, a file that
   disappears from the public repo.

**Then ask, and wait.** Ask whether to push. Do not push on silence, on a
neighbouring instruction, or on your own reading of the diff. Only an explicit
yes from the human in this conversation authorises it.

- **Yes** → push:
  ```bash
  git -C <dst> push -u origin main
  ```
  Then re-read the remote and confirm what actually landed — `git fetch` and
  check `origin/main` moved to the expected sha, and that the private files
  (`input/tracking/universe.md`, `sector-coverage.md`, `watchlist.md`, the broker
  CSVs) are absent from `origin/main`. Report that verification, not the push
  command's own output: the push succeeding says nothing about *what* it sent.
- **No, or anything ambiguous** → do not push. Leave the commit staged, say so
  plainly, and give them the command to run themselves. A staged commit is a
  perfectly good outcome; it is where this command used to end every time.

**Never create the GitHub repo, and never push to a remote you resolved by
guessing.** The remote comes from the rules at the top of this file or the human
tells you — pushing a portfolio to the wrong account is not recoverable.

## 9 — Report back

Close in this shape:

```
PUBLISH <date> — <STAGED | HALTED at step N>
Source      <this private tree>
Destination <dst>
Held back   <private providers, verbatim from publish.py>
Track rec.  <n> decisions · <n> closed trades scored · <online|offline>
Build       <n> file(s) copied, <n> excluded (allow-list)
Gates       post-conditions <PASS|FAIL> · vendor sweep <PASS|FAIL> · leak sweep <PASS|FAIL>
Commit      <sha> "<message>" — <n> file(s) changed
Push        <PUSHED origin/main <old>..<new>, verified | DECLINED — staged only | n/a — halted>
```

Then anything a reader of the public repo would notice changed since last time —
new evaluations, changed rules — one line each.

---

## Hard limits

- **Never push without an explicit yes** to step 8's question, given by the
  human in this conversation, after they have seen the full file list. Not on
  silence, not on "looks good", not because every gate went green. **Never create
  the GitHub repo** — the human makes it themselves.
- **Never edit the private tree.** This command reads from it and writes only to
  `<dst>`. If something here is wrong, say so and HALT.
- **Never run `checks.py --publish` without `--tree`** and report the result as
  the gate. Bare, it is the wrong tree either way: in the private tree it FAILs
  on the private providers sitting there, and in the published tree it skips the
  real-NAV arm entirely. Only `--tree <dst>`, run from the private tree, gives
  the check both halves of what it needs.
- **Never treat a `⚪ SKIP` on the leak sweep as a pass.** It means the sweep had
  no figures to look for — the reason it was silently useless until 2026-09-01.
- **Never work around a failed gate** by hand-deleting the offending file from
  the published tree. The gate found a hole in `publish.py`; patch that instead.
- **Never pass `--regen`,** and never copy `output/` by hand. Evaluations, the
  ledger and the intermediates carry quantities and cash; the scorecard exists
  precisely so the evidence can ship without them.
- **Never hand-edit the README track record** to satisfy a guard or to make a
  number look better. It is generated; edit the ledger or the generator.
- **Never invent the remote.** Resolve it, or HALT and ask.

---

*This canonical lives at `agents/publisher.md` and is the body of the
`/atd-publish` command on both platforms. Wrappers are generated by
`python3 tools/sync_agents.py`; editing a wrapper directly is drift that
`python3 tools/sync_agents.py --check` will fail on (invariant 8 of
`docs/TECHNICAL_ARCHITECTURE.md`).*
