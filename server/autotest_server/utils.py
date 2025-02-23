import json
import resource
import os
import zipfile
import shutil
from io import BytesIO
from typing import Type, Optional, Tuple, List, Generator
from .config import _Config


def loads_partial_json(json_string: str, expected_type: Optional[Type] = None) -> Tuple[List, bool]:
    """
    Return a list of objects loaded from a json string and a boolean
    indicating whether the json_string was malformed.  This will try
    to load as many valid objects as possible from a (potentially
    malformed) json string. If the optional expected_type keyword argument
    is not None then only objects of the given type are returned,
    if any objects of a different type are found, the string will
    be treated as malfomed.
    """
    i = 0
    decoder = json.JSONDecoder()
    results = []
    malformed = False
    json_string = json_string.strip()
    while i < len(json_string):
        try:
            obj, ind = decoder.raw_decode(json_string[i:])
            next_i = i + ind
            if expected_type is None or isinstance(obj, expected_type):
                results.append(obj)
            elif json_string[i:next_i].strip():
                malformed = True
            i = next_i
        except json.JSONDecodeError:
            if json_string[i].strip():
                malformed = True
            i += 1
    return results, malformed


def _rlimit_str2int(rlimit_string):
    return getattr(resource, f"RLIMIT_{rlimit_string.upper()}")


def get_resource_settings(config: _Config) -> list[tuple[int, tuple[int, int]]]:
    """
    Returns a list of resources and their associated rlimits.
    """
    rlimit_settings = config.get("rlimit_settings", {})
    settings_list = []

    for resource_str, rlimit in rlimit_settings.items():
        settings_list.append((_rlimit_str2int(resource_str), rlimit))

    return settings_list


def get_setrlimit_lines(resource_settings: list[tuple[int, tuple[int, int]]]) -> list[str]:
    """
    Given a list of resources and their associated rlimits, returns a list of lines, which are valid python code
    used to set the resource limits.
    """
    return [f"resource.setrlimit({_resource}, {rlimit})" for _resource, rlimit in resource_settings]


def extract_zip_stream(zip_byte_stream: bytes, destination: str) -> None:
    """
    Extract files in a zip archive's content <zip_byte_stream> to <destination>, a path to a local directory.
    """
    with zipfile.ZipFile(BytesIO(zip_byte_stream)) as zf:
        for fname in zf.namelist():
            *dpaths, bname = fname.split(os.sep)
            dest = os.path.join(destination, *dpaths)
            filename = os.path.join(dest, bname)
            if filename.endswith("/"):
                os.makedirs(filename, exist_ok=True)
            else:
                os.makedirs(dest, exist_ok=True)
                with open(filename, "wb") as f:
                    f.write(zf.read(fname))


def recursive_iglob(root_dir: str) -> Generator[Tuple[str, str], None, None]:
    """
    Walk breadth first over a directory tree starting at root_dir and
    yield the path to each directory or file encountered.
    Yields a tuple containing a string indicating whether the path is to
    a directory ("d") or a file ("f") and the path itself. Raise a
    FileNotFoundError if the root_dir doesn't exist
    """
    if os.path.isdir(root_dir):
        for root, dirnames, filenames in os.walk(root_dir):
            yield from (("d", os.path.join(root, d)) for d in dirnames)
            yield from (("f", os.path.join(root, f)) for f in filenames)
    else:
        raise FileNotFoundError("directory does not exist: {}".format(root_dir))


def copy_tree(src: str, dst: str, exclude: Tuple = tuple()) -> List[Tuple[str, str]]:
    """
    Recursively copy all files and subdirectories in the path
    indicated by src to the path indicated by dst. If directories
    don't exist, they are created. Do not copy files or directories
    in the exclude list.
    """
    copied = []
    for fd, file_or_dir in recursive_iglob(src):
        src_path = os.path.relpath(file_or_dir, src)
        if src_path in exclude or any(os.path.relpath(src_path, ex) for ex in exclude):
            continue
        target = os.path.join(dst, src_path)
        if fd == "d":
            os.makedirs(target, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(file_or_dir, target)
        copied.append((fd, target))
    return copied
