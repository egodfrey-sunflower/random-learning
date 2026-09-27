#!/usr/bin/env python3
"""Offline answer checker. Does not modify the supplied snapshot."""
import hashlib
import json
import sys

FLAG_DIGEST = 'd501a91ebba5ecf14393d1185b153f7cd6a0c00986dd1d8aa84c7a08c25f8137'
PATCH_DIGEST = 'd00418797cc8b66296523917b42a35bf5b25940ef1dda36be4643482da85d4a7'

def digest(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def number(x):
    if isinstance(x, str):
        return int(x, 0)
    if type(x) is int:
        return x
    raise ValueError('expected an integer or 0x-prefixed string')

def main():
    if len(sys.argv) != 2:
        print('Usage: python3 check.py answer.json')
        return 2
    try:
        with open(sys.argv[1], encoding='utf-8') as f:
            answer = json.load(f)
        flag = answer['flag']
        if not isinstance(flag, str):
            raise ValueError('flag must be a string')
        patch = answer['patch']
        pa = number(patch['pte_pa'])
        bits = number(patch['set_bits'])
    except (OSError, ValueError, KeyError, TypeError) as e:
        print('Cannot read answer:', e)
        return 2
    flag_ok = digest(flag) == FLAG_DIGEST
    patch_ok = digest(f'{pa}:{bits}') == PATCH_DIGEST
    print('Message:', 'recovered' if flag_ok else 'not recovered yet')
    print('Repair:', 'correct single-PTE repair' if patch_ok else 'not the required repair')
    if flag_ok and patch_ok:
        print('SUCCESS: Courier delivery restored. Guard pages remain on duty.')
        return 0
    return 1

if __name__ == '__main__':
    sys.exit(main())
