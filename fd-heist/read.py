import struct
import uuid
from dataclasses import dataclass
from typing import Literal
import json

type FileId = uuid.UUID
type PipeId = uuid.UUID
type Pid = int

def make_file_id() -> FileId:
    return uuid.uuid4()
def make_pipe_id() -> FileId:
    return uuid.uuid4()

MAX_FDS = 1_000

traces = []
with open("trace.jsonl") as f:
    for line in f:
        traces.append(json.loads(line))

with open("manifest.json") as f:
    manifest = json.loads(f.read())

# OK, so we're going to loop over a set of PIDs
# We will want to keep track of what files they have open, and what
# pipes, etc. are open.
# We also need to keep track of the state of pipes.

@dataclass
class PipeStatus:
    buffer: bytes
    open_readers: int
    open_writers: int

    def is_dead(self) -> bool:
        return self.open_readers == 0 and self.open_writers == 0

    def write(self, b: bytes) -> None:
        # We don't handle any blocking writes here.
        if self.open_readers == 0:
            assert False, "No readers are left open"
        self.buffer = self.buffer + b

    def read(self, n: int) -> bytes | None:
        if self.buffer == b"" and self.open_writers == 0:
            # This is *not* blocked - return an empty byte. 
            return b""

        # Read. None means that we should interpret this as blocked.
        if self.buffer != b"":
            b = self.buffer[:n]
            self.buffer = self.buffer[n:]
            return b
        return None

@dataclass
class FileStatus:
    file_name: str
    position: int

    def read(self, n: int, expected_length: int) -> bytes:
        # Normally we'd keep the file open, but I figured let's simulate
        # more of having to keep the position on our side.

        with open(self.file_name, "rb") as f:
            f.seek(self.position)
            b = f.read(n)
        assert len(b) == expected_length
        self.position += len(b)
        return b

@dataclass
class FileObject:
    number_of_references: int
    pipe_read: PipeId | None
    pipe_write: PipeId | None
    file: FileStatus | None

    @classmethod
    def make_initial(cls) -> "FileObject":
        return cls(number_of_references=1, pipe_read=None, pipe_write=None, file=None)

@dataclass
class BlockedRead:
    pipe_id: FileId
    buffer_name: str
    n: int
    expected_length: int
    should_capture_for_result: bool

@dataclass
class ProcessState:
    open_fds: dict[int, FileObject]
    buffers: dict[str, bytes]
    name: str

class State:
    result: bytes
    files: dict[FileId, FileObject]
    pipes: dict[PipeId, PipeStatus]
    process_state: dict[Pid, ProcessState]
    blocked_reads: dict[Pid, BlockedRead] # any PIDs that are blocked on reading from a pipe

    def __init__(self, initial_pid):
        file_id0 = make_file_id()
        file_id1 = make_file_id()
        file_id2 = make_file_id()

        file_object0 = FileObject.make_initial()
        file_object1 = FileObject.make_initial()
        file_object2 = FileObject.make_initial()

        self.files = {file_id0: file_object0, file_id1: file_object1, file_id2: file_object2}
        open_fds = {0: file_id0, 1: file_id1, 2: file_id2}

        self.process_state = {initial_pid: ProcessState(open_fds=open_fds, name="launcher", buffers={})}
        self.blocked_reads = {}
        self.pipes = {}
        self.result = b""

    def _check_blocked_reads(self, pipe_id: PipeId) -> None:
        # Check any blocked reads that might be affected by writing to pipe_id
        for (pid, blocked_read) in list(self.blocked_reads.items()):
            if blocked_read.pipe_id == pipe_id:
                result = self.pipes[pipe_id].read(blocked_read.n)
                if result is not None:
                    assert len(result) == blocked_read.expected_length
                    self.process_state[pid].buffers[blocked_read.buffer_name] = result
                    self.blocked_reads.pop(pid)

                    if blocked_read.should_capture_for_result:
                        self.result = self.result + result
                    return None

    def __repr__(self):
        return f"{self.files=},{self.process_state=},{self.blocked_reads=}"

    def _incr_file_id(self, file_id: FileId) -> None:
        assert file_id in self.files

        self.files[file_id].number_of_references += 1
        if self.files[file_id].pipe_read is not None:
            pipe_id = self.files[file_id].pipe_read
            self.pipes[pipe_id].open_readers += 1
        if self.files[file_id].pipe_write is not None:
            pipe_id = self.files[file_id].pipe_write
            self.pipes[pipe_id].open_writers += 1

    def _decr_file_id(self, file_id: FileId) -> None:
        assert file_id in self.files

        # Adjust any pipes first
        if self.files[file_id].pipe_read is not None:
            pipe_id = self.files[file_id].pipe_read
            self.pipes[pipe_id].open_readers -= 1
        elif self.files[file_id].pipe_write is not None:
            pipe_id = self.files[file_id].pipe_write
            self.pipes[pipe_id].open_writers -= 1
        else:
            pipe_id = None

        # Then tidy up files
        self.files[file_id].number_of_references -= 1
        if self.files[file_id].number_of_references == 0:
            self.files.pop(file_id)

        if pipe_id is not None:
            if self.pipes[pipe_id].is_dead():
                self.pipes.pop(pipe_id)

    def open(self, pid: Pid, file_name: str) -> None:
        # Simulate a pid opening file_name
        assert pid in self.process_state

        next_fd = None
        for i in range(0, 1_000):
            if i not in self.process_state[pid].open_fds:
                next_fd = i
                break
        assert next_fd

        file_id = make_file_id()
        file_object = FileObject.make_initial()
        file_object.file = FileStatus(file_name=file_name, position=0)

        self.process_state[pid].open_fds[next_fd] = file_id
        self.files[file_id] = file_object

    def write(self, pid: Pid, fd: int, buffer_name: str, start: int, len: int, expected_length: int) -> None:
        # Simulate a PID reading data
        assert pid in self.process_state
        assert fd in self.process_state[pid].open_fds

        file_id = self.process_state[pid].open_fds[fd]
        file_object = self.files[file_id]

        if file_object.pipe_write is None:
            print("--")
            print(pid, fd)
            print("Odd, write to fd we weren't expecting")
            print(self.process_state[pid].buffers[buffer_name][start:start+len])
            print("--")
            return

        pipe_id = file_object.pipe_write
        pipe = self.pipes[pipe_id]
        pipe.write(self.process_state[pid].buffers[buffer_name][start:start+len])
        assert expected_length == len # not supporting any partial writes here
        self._check_blocked_reads(pipe_id)
    
    def read(self, pid: Pid, fd: int, buffer_name: str, n: int, ret: int) -> None:
        # Simulate a PID reading data
        assert pid in self.process_state
        assert fd in self.process_state[pid].open_fds

        file_id = self.process_state[pid].open_fds[fd]
        file_object = self.files[file_id]
        
        should_capture_for_result = (pid == int(manifest["capture"]["pid"]) and fd == int(manifest["capture"]["fd"]))

        if file_object.pipe_read is not None:
            pipe_id = file_object.pipe_read
            pipe_status = self.pipes[pipe_id]
            output = pipe_status.read(n)
            if output is None:
                # This read is blocked
                self.blocked_reads[pid] = BlockedRead(pipe_id=pipe_id, n=n, expected_length=ret, buffer_name=buffer_name, should_capture_for_result=should_capture_for_result)
                return

            assert len(output) == ret, f"{ret=}, {len(output)=}, {output=}"
            self.process_state[pid].buffers[buffer_name] = output
        elif file_object.file is not None:
            output = file_object.file.read(n, ret)
            self.process_state[pid].buffers[buffer_name] = output
        else:
            assert False, "Not expected to read from initial fds in this"

        if should_capture_for_result:
            self.result = self.result + output

    def pipe(self, pid: Pid):
        # Create the read/write end of a pipe. 
        assert pid in self.process_state

        # Pick the file descriptors for these
        read_fd = None
        write_fd = None
        for i in range(0, 1_000):
            if i not in self.process_state[pid].open_fds:
                read_fd = i
                break
        for i in range(read_fd + 1, 1_000):
            if i not in self.process_state[pid].open_fds:
                write_fd = i
                break

        pipe_id = make_pipe_id()
        file_read_object = FileObject.make_initial()
        file_write_object = FileObject.make_initial()
        file_read_object.pipe_read = pipe_id
        file_write_object.pipe_write = pipe_id

        file_id_read = make_file_id()
        file_id_write = make_file_id()

        self.process_state[pid].open_fds[read_fd] = file_id_read
        self.process_state[pid].open_fds[write_fd] = file_id_write

        self.files[file_id_read] = file_read_object
        self.files[file_id_write] = file_write_object

        self.pipes[pipe_id] = PipeStatus(buffer=b"", open_readers=1, open_writers=1)

    def dup(self, pid: Pid, fd: int) -> None:
        # Simulate calling `dup`
        assert pid in self.process_state
        assert fd in self.process_state[pid].open_fds

        next_fd = None
        for i in range(0, 1_000):
            if i not in self.process_state[pid].open_fds:
                next_fd = i
                break
        assert next_fd is not None

        file_id = self.process_state[pid].open_fds[fd]
        self.process_state[pid].open_fds[next_fd] = file_id
        self._incr_file_id(file_id)

    def fork(self, pid: Pid, child_pid: Pid) -> None:
        assert pid in self.process_state
        assert child_pid not in self.process_state

        process_state = self.process_state[pid]

        # Copy open file descriptors, also keeping track of the reference increase.
        # (NB: We're assuming all file descriptors are *not* close-on-fork)
        open_fds = process_state.open_fds
        for file_id in open_fds.values():
            self._incr_file_id(file_id)

        new_open_fds = {file_id: file_object for (file_id, file_object) in open_fds.items()}
        # Buffers get copied, so these are separate in parent/child
        new_buffers = {buffer_name: buffer_contents for (buffer_name, buffer_contents) in process_state.buffers.items()}
        self.process_state[child_pid] = ProcessState(open_fds=new_open_fds, name=f"{process_state.name} (fork)", buffers=new_buffers)

    def close(self, pid: Pid, fd: int) -> None:
        assert pid in self.process_state
        assert fd in self.process_state[pid].open_fds

        process_state = self.process_state[pid]

        file_id = process_state.open_fds[fd]
        process_state.open_fds.pop(fd)

        self._decr_file_id(file_id)

    def exec(self, pid: Pid, name: str) -> None:
        assert pid in self.process_state
        self.process_state[pid].name = name
        self.buffers = {}
        # Assuming that no fds are close-on-exec, so these stick around!

    def exit(self, pid: Pid) -> None:
        assert pid in self.process_state
        for file_id in self.process_state[pid].open_fds.values():
            self._decr_file_id(file_id)
        self.process_state.pop(pid)

state = State(40)

for t in traces:
    pid = t["pid"]
    op = t["op"]

    if op == "read":
        fd = t["fd"]
        buffer_name = t["dst"]
        n = t["n"]
        expected_length = t["ret"]
        state.read(pid, fd, buffer_name, n, expected_length)
    elif op == "open":
        file_name = t["path"]
        file_name = manifest["files"][file_name]
        state.open(pid, file_name)
    elif op == "dup":
        fd = t["fd"]
        state.dup(pid, fd)
    elif op == "pipe":
        state.pipe(pid)
    elif op == "fork":
        child = t["child"]
        state.fork(pid, child)
    elif op == "close":
        fd = t["fd"]
        state.close(pid, fd)
    elif op == "exec":
        image = t["image"]
        state.exec(pid, image)
    elif op == "write":
        fd = t["fd"]
        buffer_name = t["src"]
        start = t["start"]
        n = t["n"]
        expected_length = t["ret"]
        state.write(pid, fd, buffer_name, start, n, expected_length)
    elif op == "exit":
        state.exit(pid)
    else:
        print(t)
        assert False

# Question 1: What's the flag? This is the collection of everything that was read into fd 0 on process 43
b = state.result
assert b[:8] == b"FDHEIST1"
n = struct.unpack("<I", b[8:12])[0]
b1 = b[12:12+n]
b2 = b[12+n:12+2*n]
plaintext = bytes(c^d for (c, d) in zip(b1, b2))
print("Plaintext:", plaintext)

# Question 2: The manifest gives a next read call that would be blocked, figure out which (pid, fd) would need to close
# to unblock it
blocked_call = manifest["halt"]["blocked_call"]
pid = blocked_call["pid"]
fd = blocked_call["fd"]

state.read(pid, fd, "foo", 10, 10)
pipe_id_of_blocked_read = state.blocked_reads[pid].pipe_id

for (pid, process_state) in state.process_state.items():
    for (fd, file_id) in process_state.open_fds.items():
        if state.files[file_id].pipe_write == pipe_id_of_blocked_read:
            print("PID/FD of the write end to this pipe", pid, fd)
