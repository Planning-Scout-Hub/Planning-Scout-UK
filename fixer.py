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

# Fix 3: ALWAYS cut everything from def run(): closing line onwards
# and replace with clean known-good ending.
# Never skip this step regardless of what is already there.
lines = src.split('\n')

run_def_idx = None
for i, l in enumerate(lines):
    if l.strip() == 'def run():':
        run_def_idx = i
        break

if run_def_idx is None:
    print("ERROR: def run(): not found")
    sys.exit(1)

# Find where run() ends: first line at column 0 after run_def_idx
run_end_idx = len(lines)
for i in range(run_def_idx + 1, len(lines)):
    l = lines[i]
    if l and not l[0].isspace():
        run_end_idx = i
        break

print(f"Fix 3: cutting everything from line {run_end_idx} onwards (was: '{lines[run_end_idx][:50] if run_end_idx < len(lines) else 'EOF'}')")

# Keep only up to end of run() body
src = '\n'.join(lines[:run_end_idx]).rstrip('\n')

# Append clean ending built line by line — no multiline strings, no heredocs
ending = []
ending.append('')
ending.append('')
ending.append('# ── Authenticate Google ──────────────────────────────────────')
ending.append('if not os.environ.get("GCP_SERVICE_ACCOUNT_JSON"):')
ending.append('    try:')
ending.append('        from google.colab import auth')
ending.append('        auth.authenticate_user()')
ending.append('        print("Google Colab auth done")')
ending.append('    except Exception:')
ending.append('        pass')
ending.append('')
ending.append('')
ending.append('if __name__ == "__main__":')
ending.append('    if args.email_only:')
ending.append('        log("Email-only mode - skipping scrape")')
ending.append('        if get_sheet():')
ending.append('            weekly_count, weekly_leads = get_weekly_lead_count()')
ending.append('            client_email = os.environ.get(CLIENT_EMAIL_VAR, "")')
ending.append('            if not client_email:')
ending.append('                log("Warning: email recipient secret not found")')
ending.append('            os.environ["GMAIL_TO"] = client_email')
ending.append('            email_digest.send_digest(')
ending.append('                [], {}, [], "", "",')
ending.append('                weekly_count=weekly_count,')
ending.append('                weekly_leads=weekly_leads,')
ending.append('                run_duration_min=0,')
ending.append('                log_fn=log,')
ending.append('            )')
ending.append('        else:')
ending.append('            log("Sheets connection failed")')
ending.append('        sys.exit(0)')
ending.append('    run()')
ending.append('')

src = src + '\n' + '\n'.join(ending)

# Fix 4: strip all trailing whitespace from every single line
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
