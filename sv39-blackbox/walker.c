// SV39 BLACKBOX -- optional C starting point.
// Build: cc -std=c11 -Wall -Wextra -O2 walker.c -o walker
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

#define PHYS_BASE UINT64_C(0x80000000)
#define RAM_SIZE (2u * 1024u * 1024u)
#define PAGE_SIZE 4096u
static unsigned char ram[RAM_SIZE];

enum result { OK, UNMAPPED, DENIED, CORRUPT, TODO };

// No guest address is a host pointer. This helper accepts physical addresses.
int phys_read(uint64_t pa, void *dst, size_t n)
{
    if (pa < PHYS_BASE || pa - PHYS_BASE > RAM_SIZE ||
        n > RAM_SIZE - (size_t)(pa - PHYS_BASE))
        return 0;
    memcpy(dst, ram + (size_t)(pa - PHYS_BASE), n);
    return 1;
}

uint64_t le64(const unsigned char *p)
{
    uint64_t n = 0;
    for (unsigned i = 0; i < 8; i++) n |= (uint64_t)p[i] << (8 * i);
    return n;
}

uint32_t le32(const unsigned char *p)
{
    uint32_t n = 0;
    for (unsigned i = 0; i < 4; i++) n |= (uint32_t)p[i] << (8 * i);
    return n;
}

// On success, write the physical byte address to *pa.
// If a leaf is reached, also return its physical PTE address via *leaf_pte_pa,
// including when access is denied. This makes a useful debugging interface.
enum result translate_user_read(uint64_t satp, uint64_t va,
                               uint64_t *pa, uint64_t *leaf_pte_pa)
{
    (void)satp; (void)va; (void)pa; (void)leaf_pte_pa;
    return TODO;
}

enum result read_user(uint64_t satp, uint64_t va, void *dst, size_t n)
{
    (void)satp; (void)va; (void)dst; (void)n;
    return TODO;
}

int main(void)
{
    FILE *f = fopen("ram.bin", "rb");
    if (!f) { perror("ram.bin (run from the challenge directory)"); return 1; }
    size_t n = fread(ram, 1, sizeof ram, f);
    int extra = fgetc(f);
    int bad = ferror(f);
    fclose(f);
    if (n != sizeof ram || extra != EOF || bad) {
        fprintf(stderr, "Unexpected RAM image size or read failure\n");
        return 1;
    }
    printf("Loaded %zu physical bytes. Implement the walker, then follow the chain.\n", n);
    // Read the running process's satp and entry_va from manifest.json.
    // Hard-coding those public constants here is fine; a JSON parser is optional.
    return 0;
}
