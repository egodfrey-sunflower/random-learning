"""Optional scaffold. Copy to solve.py and implement replay()."""
import json
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replay(manifest, events, images):
    """Return (captured_bytes, repair_pid, repair_fd).

    images maps the trace's absolute path strings to immutable file bytes.
    No real subprocesses or host file descriptors are needed.
    """
    raise NotImplementedError('Implement the trace replay and inspect the final state')


def decode_envelope(data):
    if len(data) < 16 or data[:8] != b'FDHEIST1':
        raise ValueError('Bad envelope magic or truncated header')
    n = struct.unpack_from('<I', data, 8)[0]
    if len(data) != 16 + 2 * n:
        raise ValueError('Envelope length does not match header')
    ciphertext, pad = data[12:12+n], data[12+n:12+2*n]
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, pad))
    expected_crc = struct.unpack_from('<I', data, 12 + 2*n)[0]
    if zlib.crc32(plaintext) != expected_crc:
        raise ValueError('Plaintext checksum mismatch')
    return plaintext.decode('ascii')


def main():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    events = [json.loads(line) for line in (ROOT / manifest['trace']).read_text().splitlines()]
    images = {path: (ROOT / image).read_bytes() for path, image in manifest['files'].items()}
    stream, pid, fd = replay(manifest, events, images)
    answer = {'flag': decode_envelope(stream), 'repair': {'pid': pid, 'fd': fd}}
    print(json.dumps(answer, indent=2))


if __name__ == '__main__':
    main()
