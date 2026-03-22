import ast, sys, os

PATH = "core/engine.py"
with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()
print(f"Read {len(src.splitlines())} lines")

# Fix 1: add --client to argparse if missing
if 'add_argument("--client"' not in src:
    src = src.replace(
        'parser.add_argument("--weeks"',
        'parser.add_argument("--client",     required=True,                      help="Path to client JSON")\nparser.add_argument("--weeks"',
        1
    )
    print("Fix 1: --client added")
else:
    print("Fix 1: --client already present")

# Fix 2: remove email_only block from inside run()
lines = src.split('\n')
new_lines = []
i = 0
skip = False
fixed2 = False
while i < len(lines):
    line = lines[i]
    if line == 'def run():':
        new_lines.append(line)
        i += 1
        continue
    if not skip and line.strip().startswith('run_start = datetime.now()'):
        new_lines.append('    run_start = datetime.now()')
        skip = True
        i += 1
        continue
    if skip:
        if lines[i].strip().startswith('today = datetime.now()'):
            new_lines.append('    today = datetime.now()')
            skip = False
            fixed2 = True
            i += 1
            continue
        else:
            i += 1
            continue
    new_lines.append(line)
    i += 1
src = '\n'.join(new_lines)
print(f"Fix 2: email_only removed from run() = {fixed2}")

# Fix 3: find def run(): and cut EVERYTHING after the closing of that function.
# We keep lines from start up to (but not including) the first line at col 0
# that appears after def run(): — whether it's if __name__, a comment, or run().
# Then we append a clean known-good ending.
lines = src.split('\n')

# Find def run():
run_def_idx = None
for i, l in enumerate(lines):
    if l.strip() == 'def run():':
        run_def_idx = i
        break

if run_def_idx is None:
    print("ERROR: def run(): not found")
    sys.exit(1)

# Find the LAST line that belongs to run() — scan backwards from end of file
# to find where the indented block of run() ends
run_end_idx = len(lines)
for i in range(run_def_idx + 1, len(lines)):
    l = lines[i]
    # A line at col 0 that is non-empty and non-comment = end of function
    if l and not l[0].isspace():
        run_end_idx = i
        break

print(f"Fix 3: cutting from line {run_end_idx} ('{lines[run_end_idx][:60] if run_end_idx < len(lines) else 'EOF'}')")

# Keep only lines that are part of run() and before
src = '\n'.join(lines[:run_end_idx]).rstrip('\n')

# Append clean ending
src += '\n\n# ── Authenticate Google ──────────────────────────────────────\n'
src += 'if not os.environ.get("GCP_SERVICE_ACCOUNT_JSON"):\n'
src += '    try:\n'
src += '        from google.colab import auth\n'
src += '        auth.authenticate_user()\n'
src += '        print("Google Colab auth done")\n'
src += '    except Exception:\n'
src += '        pass\n'
src += '\n'
src += 'if __name__ == "__main__":\n'
src += '    if args.email_only:\n'
src += '        log("Email-only mode - skipping scrape")\n'
src += '        if get_sheet():\n'
src += '            weekly_count, weekly_leads = get_weekly_lead_count()\n'
src += '            client_email = os.environ.get(CLIENT_EMAIL_VAR, "")\n'
src += '            if not client_email:\n'
src += '                log("Warning: email recipient secret not found")\n'
src += '            os.environ["GMAIL_TO"] = client_email\n'
src += '            email_digest.send_digest(\n'
src += '                [], {}, [], "", "",\n'
src += '                weekly_count=weekly_count,\n'
src += '                weekly_leads=weekly_leads,\n'
src += '                run_duration_min=0,\n'
src += '                log_fn=log,\n'
src += '            )\n'
src += '        else:\n'
src += '            log("Sheets connection failed")\n'
src += '        sys.exit(0)\n'
src += '    run()\n'

# Fix 4: strip all trailing whitespace
src = '\n'.join(l.rstrip() for l in src.split('\n')).rstrip('\n') + '\n'
print("Fix 4: trailing whitespace stripped")

# Syntax check
try:
    ast.parse(src)
    print("SYNTAX: CLEAN")
except SyntaxError as e:
    print(f"SYNTAX ERROR line {e.lineno}: {e.msg}")
    ctx = src.split('\n')
    for j, l in enumerate(ctx[max(0, e.lineno-4):e.lineno+4], start=max(1, e.lineno-3)):
        print(f"  {j}: {repr(l)}")
    sys.exit(1)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)
print(f"Done. {len(src.splitlines())} lines written to {PATH}")
