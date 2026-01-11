

import os
import re

def get_unique_filepath(directory: str, base_name: str, extension: str) -> str:

    if not extension.startswith('.'):
        extension = f'.{extension}'

    base_name = os.path.splitext(base_name)[0]
    full_path = os.path.join(directory, f"{base_name}{extension}")

    if not os.path.exists(full_path):
        return full_path

    match = re.match(r"^(.*?) \((\d+)\)$", base_name)
    if match:
        clean_base = match.group(1)
        counter = int(match.group(2)) + 1
    else:
        clean_base = base_name
        counter = 1

    while True:
        new_name = f"{clean_base} ({counter})"
        new_path = os.path.join(directory, f"{new_name}{extension}")
        if not os.path.exists(new_path):
            return new_path
        counter += 1

