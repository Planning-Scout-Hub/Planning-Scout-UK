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

# Fix 3: replace bare run() at end with __main__ block
main_block = """

if __name__ == "__main__":
    if args.email_only:
        log("Email-only mode - skipping scrape")
        if get_sheet():
            weekly_count, weekly_leads = get_weekly_lead_count()
            client_email = os.environ.get(CLIENT_EMAIL_VAR, "")
            if not client_email:
                log("Warning: email recipient secret not found")
            os.environ["GMAIL_TO"] = client_email
            email_digest.send_digest(
                [], {}, [], "", "",
                weekly_count=weekly_count,
                weekly_leads=weekly_leads,
                run_duration_min=0,
                log_fn=log,
            )
        else:
            log("Sheets connection failed")
        sys.exit(0)
    run()
"""

if 'if __name__ == "__main__":' in src:
    print("Fix 3: __main__ already present")
elif '\nrun()\n' in src:
    idx = src.rfind('\nrun()\n')
    src = src[:idx] + main_block
    print("Fix 3: __main__ block added")
else:
    src = src.rstrip('\n') + main_block
    print("Fix 3: __main__ appended")

# Fix 4: strip all trailing whitespace from every line
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
