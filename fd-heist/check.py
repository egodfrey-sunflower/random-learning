#!/usr/bin/env python3
"""Checks answers, not the internals of your replay implementation."""
import hashlib
import json
import sys
from pathlib import Path

FLAG_SHA256 = '79fbf4b1dd4a8f1ebbade133fafe3ce70bb15562739984a2abe39d001ffcabc3'
REPAIR_SHA256 = 'fb7dc5d406c01c48e791beac072de902a8c3668c50bda3502bba9ff12e8ff118'

def main():
    if len(sys.argv) != 2:
        print('Usage: python3 check.py answer.json')
        return 2
    try:
        answer = json.loads(Path(sys.argv[1]).read_text())
        flag = answer['flag']
        repair = answer['repair']
        pid, fd = repair['pid'], repair['fd']
        if not isinstance(flag, str) or type(pid) is not int or type(fd) is not int:
            raise ValueError('flag must be text; pid and fd must be integers')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('Invalid answer:', exc)
        return 2
    recovered = hashlib.sha256(flag.encode()).hexdigest() == FLAG_SHA256
    fixed = hashlib.sha256(f'{pid}:{fd}'.encode()).hexdigest() == REPAIR_SHA256
    print('Message: ' + ('recovered' if recovered else 'incorrect'))
    print('Repair: ' + ('correct single-descriptor close' if fixed else 'incorrect'))
    if recovered and fixed:
        print('SUCCESS: Message recovered. The last writer is gone; the receiver sees EOF.')
        return 0
    return 1

if __name__ == '__main__':
    sys.exit(main())
