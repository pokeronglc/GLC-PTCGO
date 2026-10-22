"""Builds one virtual type-split bundle in a short-lived child process.

A virtual split (e.g. ``en_US_SM5_fighting``) is the physical set bundle with
its CAB renamed so the client treats it as a separate bundle.  Parsing and
re-packing an ~84 MB bundle with UnityPy peaks at several hundred MB, and the
Python allocator rarely hands that memory back to the OS.  Done inside the
long-running server, each build ratcheted RSS up until a 4 GB VPS was
OOM-killed a few minutes into a game.  Running each build in its own process
returns all of that memory the moment the child exits.

Usage: python -m spirit.server.virtual_split_worker SRC OUT CAB_NAME
Writes the rebuilt bundle to OUT (atomically) and exits 0.
"""
import hashlib
import logging
import os
import sys


def rename_cab(file_bytes: bytes, new_cab_name: str, physical_bundle_name: str) -> bytes:
    try:
        import UnityPy
        env = UnityPy.load(file_bytes)
        if hasattr(env, 'file') and hasattr(env.file, 'files'):
            for old_key in [k for k in env.file.files.keys() if k.startswith('CAB-')]:
                env.file.files[new_cab_name] = env.file.files.pop(old_key)
        for asset in env.assets:
            if hasattr(asset, 'name') and asset.name.startswith('CAB-'):
                asset.name = new_cab_name
        return env.file.save(packer="lz4")
    except Exception as e:  # mock/non-standard bundles (test suites)
        logging.warning(f"[HTTP] UnityPy CAB customize failed ({e}); raw byte replacement fallback.")
        new_cab_bytes = new_cab_name.encode('utf-8')
        old_cab_legacy = b"CAB-698f1293cb9396443b3f13ebe0cec855"
        h_phys = hashlib.md5(physical_bundle_name.encode('utf-8')).hexdigest()
        old_cab_phys = f"CAB-{h_phys}".encode('utf-8')
        if old_cab_legacy in file_bytes:
            file_bytes = file_bytes.replace(old_cab_legacy, new_cab_bytes)
        if old_cab_phys in file_bytes:
            file_bytes = file_bytes.replace(old_cab_phys, new_cab_bytes)
        return file_bytes


def build_to_file(src: str, out: str, new_cab_name: str) -> None:
    with open(src, 'rb') as f:
        data = f.read()
    physical = os.path.basename(os.path.dirname(os.path.dirname(src)))
    data = rename_cab(data, new_cab_name, physical)
    tmp = f"{out}.{os.getpid()}.tmp"
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, out)


def main(argv):
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    build_to_file(argv[1], argv[2], argv[3])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
