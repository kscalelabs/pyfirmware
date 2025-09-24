#!/usr/bin/env python3
"""
io_bench_fixed.py — same as before but robust to missing dirs/files.
Usage:
    python io_bench_fixed.py /tmp/shm/test /tmp/test
"""
import argparse, os, time, shutil, random, sys

MB = 1024 * 1024
KB = 1024

def detect_mount_type(path):
    path = os.path.abspath(path)
    best = ("", "")
    with open("/proc/mounts", "r") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3:
                mntpoint, fstype = parts[1], parts[2]
                if path.startswith(mntpoint) and len(mntpoint) > len(best[1]):
                    best = (fstype, mntpoint)
    return best[0] if best[1] else "unknown"

def ensure_parent(path):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)

def available_bytes(path):
    try:
        usage = shutil.disk_usage(path)
        return usage.free
    except Exception:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize

def preallocate_file(path, size):
    # create/truncate file to requested size
    with open(path, "w+b") as f:
        f.truncate(size)
        f.flush()
        os.fsync(f.fileno())

def seq_write(path, total_bytes, blk_bytes, do_fsync=True):
    data = b"\x00" * blk_bytes
    start = time.perf_counter()
    written = 0
    with open(path, "wb") as f:
        while written < total_bytes:
            towrite = min(blk_bytes, total_bytes - written)
            f.write(data[:towrite])
            written += towrite
        if do_fsync:
            f.flush()
            os.fsync(f.fileno())
    end = time.perf_counter()
    return written, end - start

def seq_read(path, blk_bytes):
    total = 0
    start = time.perf_counter()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(blk_bytes)
            if not chunk:
                break
            total += len(chunk)
    end = time.perf_counter()
    return total, end - start

def rnd_io(path, file_size, op_bytes, ops, write=False):
    # Ensure file exists and has requested size
    if not os.path.exists(path):
        preallocate_file(path, file_size)
    mode = "r+b" if os.path.exists(path) else "w+b"
    with open(path, mode) as f:
        # ensure size is visible to the kernel
        f.flush(); os.fsync(f.fileno())
        start = time.perf_counter()
        for _ in range(ops):
            off = random.randrange(0, max(1, file_size - op_bytes + 1))
            f.seek(off)
            if write:
                f.write(b"\xAA" * op_bytes)
            else:
                f.read(op_bytes)
        if write:
            f.flush(); os.fsync(f.fileno())
        end = time.perf_counter()
    return ops, end - start

def fmt_rate(bytes_count, sec):
    mb_s = bytes_count / sec / MB if sec > 0 else 0.0
    return f"{mb_s:7.2f} MB/s"

def fmt_iops(ops, sec):
    iops = ops / sec if sec > 0 else 0.0
    return f"{iops:8.2f} IOPS"

def run_on_target(basepath, size_mb, blk_kb, rnd_kb, rnd_ops, cleanup):
    try:
        ensure_parent(basepath)
    except Exception as e:
        print(f"ERROR: cannot create parent dir for {basepath}: {e}")
        return

    fstype = detect_mount_type(basepath)
    free = available_bytes(os.path.dirname(basepath) or "/")
    want = size_mb * MB
    if want > free:
        want = max(int(free * 0.8), 16 * MB)
    seq_blk = blk_kb * KB
    rnd_blk = rnd_kb * KB

    print(f"\n== {basepath}  (fstype={fstype})")
    print(f"Using file of {want//MB} MiB, seq block {seq_blk//KB} KiB, rnd block {rnd_blk} B, rnd ops {rnd_ops}")

    try:
        written, t = seq_write(basepath, want, seq_blk, do_fsync=True)
        print("seq write+fsync:", fmt_rate(written, t), f"({written//MB} MiB in {t:.2f}s)")
    except Exception as e:
        print("seq write failed:", e); return

    try:
        read_b, tr = seq_read(basepath, seq_blk)
        print("seq read      :", fmt_rate(read_b, tr), f"({read_b//MB} MiB in {tr:.2f}s)")
    except Exception as e:
        print("seq read failed:", e); return

    try:
        with open(basepath, "r+b") as f:
            f.seek(0)
            f.write(b"\x01")
            f.flush()
            t0 = time.perf_counter()
            os.fsync(f.fileno())
            t1 = time.perf_counter()
        print("single fsync   :", f"{(t1-t0)*1000:7.2f} ms")
    except Exception as e:
        print("fsync test failed:", e)

    try:
        ops, trnd = rnd_io(basepath, want, rnd_blk, rnd_ops, write=False)
        print("random read    :", fmt_iops(ops, trnd), fmt_rate(ops * rnd_blk, trnd))
    except Exception as e:
        print("random read failed:", e)

    try:
        opsw, trw = rnd_io(basepath, want, rnd_blk, rnd_ops, write=True)
        print("random write   :", fmt_iops(opsw, trw), fmt_rate(opsw * rnd_blk, trw))
    except Exception as e:
        print("random write failed:", e)

    if cleanup:
        try:
            os.remove(basepath)
        except Exception:
            pass
    else:
        print(f"Leaving file: {basepath}")

def main():
    p = argparse.ArgumentParser(description="Robust I/O benchmark for two paths")
    p.add_argument("paths", nargs=2, help="two test file paths (e.g. /tmp/shm/test /tmp/test)")
    p.add_argument("--size-mb", type=int, default=512)
    p.add_argument("--blk-kb", type=int, default=4096)
    p.add_argument("--rnd-kb", type=int, default=4)
    p.add_argument("--rnd-ops", type=int, default=10000)
    p.add_argument("--no-clean", action="store_true", help="don't delete test files after run")
    args = p.parse_args()

    random.seed(12345)
    for path in args.paths:
        run_on_target(path, args.size_mb, args.blk_kb, args.rnd_kb, args.rnd_ops, cleanup=not args.no_clean)

if __name__ == "__main__":
    main()
