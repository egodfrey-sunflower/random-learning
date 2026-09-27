# SV39 BLACKBOX: The courier's last message

A courier process crashed before delivering its final message. You have a
physical RAM snapshot and a debugger's register log. The message is still there,
but its fragments are linked by **virtual** addresses. The courier was also
experimenting with its page permissions. One legitimate leaf PTE lost its user
access bit.

Your mission: recover the flag from PID 17, and identify the **one PTE** that
needs repair. A repair may only set `PTE_U` on that existing leaf. It must not
change any physical page number, grant write/execute access, or make a guard
page or trampoline accessible to user code.

This is a synthetic xv6-like snapshot, not a bootable xv6 image. It uses the
Sv39 layout from chapter 3. Budget roughly 60–90 minutes; you can use any language.
There are no dependencies beyond Python 3 for the checker, plus a C compiler
if you use the optional starter.

## Start here

```sh
cat manifest.json
cc -std=c11 -Wall -Wextra -O2 walker.c -o walker
./walker
```

`ram.bin` is physical memory, beginning at the physical base in `manifest.json`.
Thus file offset zero corresponds to that base, not physical address zero.
`manifest.json` records two processes. Use the running courier's `satp`.
Each process owns a different root page table; equal virtual addresses do not
necessarily refer to equal physical addresses.

Implement these operations (the starter leaves their bodies to you):

1. Translate a virtual address by walking the three-level tree. Return distinct
   results for an absent mapping, denied user access, and corrupt/out-of-range
   page-table data. On success return the **byte** physical address, not just
   the physical page base.
2. Read an arbitrary range of user virtual memory. Reads can cross a page
   boundary even when the underlying physical pages are unrelated.
3. Follow the record chain beginning at `entry_va`. Decode and concatenate its
   payloads in chain order.
4. When a legitimate read hits the damaged PTE, identify the leaf's physical
   address. Apply the permitted repair in memory and finish the recovery.

Work on a copy in memory. Keep the supplied snapshot unchanged.

## Wire format

Every record is exactly 32 bytes, encoded little-endian:

| Byte offset | Type | Meaning |
| --- | --- | --- |
| 0 | uint64 | Virtual address of next record; zero ends the chain |
| 8 | uint64 | Virtual address of encoded payload |
| 16 | uint32 | Payload length in bytes |
| 20 | uint32 | Salt |
| 24 | uint64 | Magic, as listed in the manifest |

Records and payloads may straddle pages. Do not assume a record fits inside
one physical allocation. The chain contains `expected_records` records.

For payload byte index `j` (starting at zero for **each record**), translate
`payload_va + j` to its physical byte address `pa`, then decode:

```text
mask = ((pa >> 12) XOR salt XOR j) AND 0xff
plain[j] = encoded[j] XOR mask
```

This encoding is just a puzzle mechanism, not cryptography. The byte's physical
page number is deliberately part of it. Do not reset `j` at page boundaries.

## Machine contract

- All addresses in this puzzle are below xv6's `MAXVA = 1 << 38`.
- `satp[63:60]` is mode 8 (Sv39); `satp[43:0]` holds the root physical page number.
- Each page table is a 4096-byte page of 512 little-endian 64-bit PTEs.
- PTE bits 0–7 are V, R, W, X, U, G, A, D. Bits 53–10 hold the PPN.
- A valid non-leaf has R=W=X=0. Leaf mappings are at level 0 only; no superpages.
- User reads need a valid leaf with R and U set. U on a non-leaf does not grant
  user access. The snapshot's non-leaf reserved bits are zero.
- There are no TLBs, races, swapped-out pages, or hidden page-fault handlers in
  this offline puzzle. A/D bits are already initialized; do not modify them.
- Supervisor-only mappings are intentional **except for exactly one leaf used
  by the live record chain**. The protected addresses in the manifest are not
  part of that chain and must remain inaccessible in user mode.

Consulting xv6 `walk`, `walkaddr`, or `copyin` is fair game. For an extra challenge,
try it from the book's diagrams first. Reading physical memory while debugging
is allowed; silently bypassing U checks to finish the chain is not the repair.

## Submit locally

Create `answer.json` using this shape (replace the placeholders):

```json
{
  "flag": "flag{your_recovered_message}",
  "patch": {
    "pte_pa": "0xPHYSICAL_ADDRESS_OF_THE_PTE",
    "set_bits": "0x10"
  }
}
```

```sh
python3 check.py answer.json
```

The checker only contains hashes of the expected answers; it does not ship a
walk implementation or plaintext solution. It verifies your submitted flag and
patch, not the internals of your walker. There is no network or submission server.

## Victory lap

Once you pass, explain these using evidence from your program:

- Which three indices, PTE addresses, and PTE values translate `entry_va`?
- Where does the first record cross a page boundary, and which physical pages
  contain its two parts?
- Why did the bad PTE allow the kernel to inspect the bytes but deny user access?
- Why would setting U on every valid PTE be wrong?
- Why can a physical page address from a PTE be used as a pointer inside xv6's
  kernel, but not as a pointer in this host-side tool?

Ask Astra for a hint at the level you want: conceptual nudge, pseudocode, or code
review. No solution or hidden hint files are included in this directory.
