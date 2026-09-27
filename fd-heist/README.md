# FD HEIST: The last writer

The courier is back. This time its message passed through a small Unix pipeline.
The receiver collected some bytes, then hung forever waiting for the end of the
stream. Every intended sender claims to have exited.

You recovered two file images and a globally ordered syscall trace. The logger
recorded buffer names and byte counts, but **not buffer contents**. Reconstruct
the receiver's input, recover the flag, and identify the **one descriptor** that
must be closed to let the receiver finish.

This is a synthetic xv6-like forensic exercise based on chapters 1–3, primarily
the process and file-descriptor interfaces. No later chapters, kernel build,
scheduling simulator, or real child processes are needed. Allow roughly 2–3
hours. Python's standard library is enough; any language is fine.

## Evidence

- `manifest.json`: initial state, file-image mapping, target receiver, final halt,
  and message format.
- `trace.jsonl`: 103 events involving six processes, one JSON object per line.
- `images/`: immutable contents of the two regular files used by the trace.
- `starter.py`: optional loading scaffold. Copy it to `solve.py` if useful.
- `check.py`: local answer checker; expected answers are stored as hashes.

Start by reading the manifest and the first few trace events. Your implementation
should work through the supplied trace rather than spawn processes on your host.
Keep the evidence files unchanged.

## Your tasks

1. Replay the trace and reconstruct the bytes returned by the receiver's reads,
   as specified by `manifest.capture`. Concatenate **each read's returned bytes**
   in trace order, even when later reads overwrite the same named buffer.
2. Decode the resulting envelope and recover its flag. Validate both its magic
   and its checksum so you can distinguish a plausible prefix from a good replay.
3. At the halt, identify one `(pid, fd)` whose closure makes the receiver's pending
   read return EOF. It must belong to another live process. No process may be
   killed, no data may be injected, and no earlier event may be changed.

Recovery and repair are separate tasks. It's fine to inspect all the evidence
offline; you do not need to pretend to be constrained by a process's permissions.

## Trace contract

Events are in their actual global execution order. All listed operations completed
successfully. They run one at a time, with no interleaving inside a syscall. The
only incomplete syscall is the final read described in `manifest.halt`; it is
**not** a completed event in `trace.jsonl`.

Initially only `manifest.initial_pid` exists. Its buffer map is empty. Descriptors
0, 1, and 2 refer to the console; no other descriptors exist. Console writes can
be discarded. No console reads occur. The console never aliases a regular file
or a pipe.

Descriptor-allocating return values were redacted. Derive them using the rules
below. `fork.child` was retained so you can follow the processes. `read.ret` and
`write.ret` are observed return counts, and are useful consistency checks.

| Operation | Trace fields | Meaning |
| --- | --- | --- |
| `open` | `path` | Open an existing regular file read-only. Allocate the lowest unused fd. Each open creates a new open-file object with offset zero. |
| `dup` | `fd` | Allocate the lowest unused fd referring to the **same** open-file object as `fd`. |
| `pipe` | none | Create an empty pipe. Allocate its read end first, then its write end, each at the lowest unused fd. |
| `fork` | `child` | Create that child PID. Copy the parent's descriptor table, retaining references to the same open-file objects. Copy its named buffers by value. Both processes continue independently. |
| `exec` | `image` | Replace the process image. Clear its named buffers. Preserve its PID and every open descriptor. `image` is a label, not an executable you need to find. |
| `close` | `fd` | Remove this one descriptor from this process. Other aliases remain valid. |
| `read` | `fd`, `n`, `dst`, `ret` | Request up to `n` bytes; replace this process's named buffer `dst` with exactly the bytes returned. |
| `write` | `fd`, `src`, `start`, `n`, `ret` | Write the slice `src[start:start+n]` from this process's current named buffer. All writes here complete in full. |
| `exit` | `status` | Close every descriptor belonging to this process and discard its buffers. It performs no further operations. |

The fd limit is 16, numbered 0–15. All allocations fit. No operation uses a closed
descriptor, an uninitialized buffer, or an out-of-bounds buffer slice. There is no
implicit `dup2`, `lseek`, close-on-exec, inherited access to another process's
buffer mutations, or unlogged I/O. Every event appears explicitly.

Named buffers are a trace abstraction for user memory: a read replaces the entire
named buffer, writes do not modify it, and `fork` copies it. You do not need to
simulate virtual addresses, stale bytes beyond a read's return count, or ELF loading.

### File and pipe behavior

A regular-file read starts at the referenced open-file object's current offset,
returns up to `n` bytes (limited by file length), and advances that object's offset
by the number returned. Opening the same path twice shares the underlying file
contents but creates separate offsets. `dup` and `fork` preserve sharing of an
existing open-file object and its offset. File contents never change in this trace.

A pipe is a FIFO **byte stream**. Writes append bytes; reads consume them. Writes
do not create records. Under this trace's serial execution, a read on a nonempty
pipe returns `min(n, queued_bytes)`, even if some writer remains alive. Pipe
capacity is 512 bytes and every recorded write fits without blocking; a read end
exists for every write.

For a positive-length read on an empty pipe:

- If any process still holds any descriptor referring to its write end, it blocks.
- If no such descriptors remain, it returns zero: EOF.

The last rule concerns references to **this pipe's write end**, not simply whether
a process named `sender` has exited. Exited processes retain no descriptors,
even if their process-table entries have not yet been reaped.

## Envelope

The captured stream is exactly one envelope, with no padding or trailing bytes:

| Offset | Size | Content |
| --- | --- | --- |
| 0 | 8 | ASCII `FDHEIST1` |
| 8 | 4 | Unsigned plaintext length `n`, little-endian |
| 12 | `n` | Ciphertext |
| `12+n` | `n` | Pad |
| `12+2*n` | 4 | CRC-32 of plaintext, little-endian |

Decode each byte as `plaintext[j] = ciphertext[j] XOR pad[j]`. The plaintext is
an ASCII flag. CRC-32 is the value produced by Python's `zlib.crc32(plaintext)`.
This encoding hides a direct string search; it is not a cryptography challenge.
There are no alternative flags or intentionally malformed records in the evidence.

## Submit

Create `answer.json` with this shape (replace the placeholders):

```json
{
  "flag": "flag{your_recovered_message}",
  "repair": {"pid": 123, "fd": 9}
}
```

```sh
python3 check.py answer.json
```

The checker verifies the flag and repair separately. It does not inspect your
replay implementation or modify the trace. Brute-forcing the small repair space
against its hash would skip that part of the exercise; use the descriptor state
to find it instead. No solution script or plaintext answer is shipped.

## After you solve it

Use your reconstructed state to explain:

- How can two processes reading the same fd number affect one another's position?
- How can two descriptors for the same path have independent positions?
- Which bytes came from a buffer copied by `fork`, and why did a later parent read
  not change that child's copy?
- Which read crossed a write boundary, and which returned fewer bytes than requested?
- Through which events did the unwanted write-end reference reach its final owner?
- Why would closing the receiver's own descriptor be a different outcome from EOF?

If useful, consult the [xv6 chapter on OS interfaces](https://mit-pdos.github.io/xv6-riscv-book/unix.html)
and the implementations of [descriptor allocation](https://github.com/mit-pdos/xv6-riscv/blob/riscv/kernel/sysfile.c),
[file objects](https://github.com/mit-pdos/xv6-riscv/blob/riscv/kernel/file.c),
and [pipes](https://github.com/mit-pdos/xv6-riscv/blob/riscv/kernel/pipe.c).
Ask for a conceptual hint, a state-model hint, or a code review when you want one.
