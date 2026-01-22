import json
import subprocess
import argparse
import sys


def run_request(tool: str, args: dict):
    req = {"id": 1, "tool": tool, "args": args}
    payload = json.dumps(req, ensure_ascii=False) + "\n"

    proc = subprocess.Popen([sys.executable, "server.py"], cwd='.', stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        out, err = proc.communicate(input=payload, timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()

    if err:
        print("--- STDERR ---")
        print(err, end='')
    print("--- STDOUT ---")
    print(out, end='')

    # Try to find a JSON line in stdout
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if obj.get('id') == 1:
                print('\nParsed response:')
                print(json.dumps(obj, indent=2, ensure_ascii=False))
                return obj
        except Exception:
            continue

    print('\nNo valid JSON response found in stdout.')
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tool', default='generate_test_credentials')
    parser.add_argument('--arg', action='append', help='arg in key=value form', default=[])
    args = parser.parse_args()

    arg_dict = {}
    for a in args.arg:
        if '=' in a:
            k, v = a.split('=', 1)
            # try to interpret ints
            if v.isdigit():
                v_parsed = int(v)
            else:
                v_parsed = v
            arg_dict[k] = v_parsed

    run_request(args.tool, arg_dict)


if __name__ == '__main__':
    main()
