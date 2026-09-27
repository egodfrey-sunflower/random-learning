from dataclasses import dataclass
import json
import struct

PAGE_SIZE = 4096

with open("manifest.json") as f:
    manifest = json.loads(f.read())

with open("ram.bin", "rb") as f:
    ram = f.read()

assert manifest["physical_size"] == len(ram)

def satp_to_root_page_table_number(satp: int) -> int:
    # Get physical page of root page table
    # see https://docs.amd.com/r/en-US/ug1629-microblaze-v-user-guide/Supervisor-Address-Translation-and-Protection-Register-satp
    mode_flag = (satp >> 60)
    asid_flag = (satp >> 44) & ((1 << 16) - 1)
    assert mode_flag == 8 # sv39 flag
    return satp & ((1 << 44) - 1)

def get_page(physical_page_number: int) -> bytes:
    base = int(manifest["physical_base"], 16)
    target = physical_page_number * PAGE_SIZE
    return ram[target - base : target - base + PAGE_SIZE]

def get_byte(physical_address: int) -> bytes:
    base = int(manifest["physical_base"], 16)
    return ram[physical_address - base]

@dataclass
class PageTableEntry:
    physical_page_number: int
    read_flag: int
    write_flag: int
    execute_flag: int
    user_flag: int

def read_page_table(page_number: int, entry_number: int) -> PageTableEntry | None:
    b = get_page(page_number)
    assert len(b) == PAGE_SIZE
    result = []

    pte = b[entry_number * 8: entry_number * 8 + 8]
    pte = struct.unpack("<Q", pte)[0]
    valid = pte & 1

    if not valid: 
        return None

    read_flag = (pte >> 1) & 1
    write_flag = (pte >> 2) & 1
    execute_flag = (pte >> 3) & 1
    user_flag = (pte >> 4) & 1

    physical_page_number = (pte >> 10)

    pte = PageTableEntry(physical_page_number=physical_page_number, read_flag=read_flag, write_flag=write_flag, execute_flag=execute_flag, user_flag=user_flag)

    return pte

def virtual_to_physical_address(va: int, satp: int) -> int:
    page_offset = va & ((1 << 12) - 1)
    virtual_page_number = va >> 12

    level0_number = virtual_page_number >> 18
    level1_number = (virtual_page_number >> 9) & ((1<<9) - 1)
    level2_number = virtual_page_number & ((1<<9) - 1)

    root_page_number = satp_to_root_page_table_number(satp)
    pte0 = read_page_table(root_page_number, level0_number)
    pte1 = read_page_table(pte0.physical_page_number, level1_number)
    pte2 = read_page_table(pte1.physical_page_number, level2_number)

    if not pte2.user_flag:
        print(f"WARNING, PTE at {pte1.physical_page_number}, {level2_number} not user readable")
        print(f"This is {hex(pte1.physical_page_number * PAGE_SIZE + level2_number * 8)}")

    return (pte2.physical_page_number * PAGE_SIZE) + page_offset

satp = int(manifest["processes"][1]["satp"], 16)
entry_va = int(manifest["entry_va"], 16)

@dataclass
class RecordMetadata:
    next_va: int
    payload_va: int
    payload_len: int
    salt: int
    magic: int

    @classmethod
    def of_bytes(cls, b: bytes) -> "RecordMetadata":
        assert len(b) == 32
        (next_va, payload_va, payload_len, salt, magic) = struct.unpack("<QQIIQ", b)

        assert magic == int(manifest["record_magic"], 16)
        return cls(next_va=next_va, payload_va=payload_va, payload_len=payload_len, salt=salt, magic=magic)

def read_metadata(virtual_address: int, satp: int) -> RecordMetadata:
    b = bytes(get_byte(virtual_to_physical_address(i, satp)) for i in range(virtual_address, virtual_address + 32))
    return RecordMetadata.of_bytes(b)

def read_data(metadata: RecordMetadata, satp: int) -> bytes:
    result = []

    for byte_number in range(metadata.payload_len):
        va = metadata.payload_va + byte_number
        physical_address = virtual_to_physical_address(va, satp)
        physical_page = physical_address >> 12

        mask = (physical_page ^ metadata.salt ^ byte_number) & 0xff
        result.append(get_byte(physical_address) ^ mask)

    return bytes(result)

# Read the linked list of metadata in memory (this might spill across page tables)
metadata_records = [read_metadata(entry_va, satp)]
while True:
    next_ = metadata_records[-1].next_va
    if next_ == 0: break

    metadata_records.append(read_metadata(next_, satp))

data = b""
for metadata_record in metadata_records:
    print(metadata_record)
    data = data + read_data(metadata_record, satp)

print(data)
