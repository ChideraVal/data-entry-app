import json
from typing import Any, Dict


# FLATTEN ROWS

PRIMITIVES = (str, int, float, bool, type(None))

def flatten(
    value: Any,
    *,
    prefix: str = "",
    depth: int = 0,
    max_depth: int = 2
) -> Dict[str, Any]:
    """
    Flattens a JSON-like structure into a flat dict using dot notation.

    Arrays are always serialized as *_json.
    Objects are flattened until max_depth is reached.
    """

    flat: Dict[str, Any] = {}

    # 1️⃣ Primitive → assign directly
    if isinstance(value, PRIMITIVES):
        flat[prefix] = value
        return flat

    # 2️⃣ Depth limit reached → serialize
    if depth >= max_depth:
        flat[prefix + "_json"] = json.dumps(value)
        return flat

    # 3️⃣ Dict → recurse
    if isinstance(value, dict):
        for key, val in value.items():
            new_prefix = f"{prefix}.{key}" if prefix else key
            flat.update(
                flatten(
                    val,
                    prefix=new_prefix,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
            )
        return flat

    # 4️⃣ List → always JSON
    if isinstance(value, list):
        flat[prefix + "_json"] = json.dumps(value)
        return flat

    # 5️⃣ Fallback (should never happen)
    flat[prefix] = str(value)
    return flat



# BUILD ROWS FROM DOCUMENT

from typing import Any, Dict, List, Optional

def get_by_path(obj: Dict[str, Any], path: str) -> Any:
    """
    Safely fetches a value from a dict using dot notation.
    """
    current = obj
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def remove_by_path(obj: Dict[str, Any], path: str) -> Dict[str, Any]:
    """
    Returns a copy of obj with the given path removed.
    """
    if "." not in path:
        new = dict(obj)
        new.pop(path, None)
        return new

    head, *rest = path.split(".")
    if head not in obj or not isinstance(obj[head], dict):
        return dict(obj)

    new = dict(obj)
    new[head] = remove_by_path(obj[head], ".".join(rest))
    return new


def build_rows_from_document(
    document: Dict[str, Any],
    *,
    row_source: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Returns a list of row objects extracted from a document.
    """

    # 1️⃣ No row source → whole document = one row
    if not row_source:
        return [document]

    rows = get_by_path(document, row_source)

    # 2️⃣ Invalid row source → fallback
    if not isinstance(rows, list):
        return [document]

    # 3️⃣ Ensure array of objects
    if not all(isinstance(item, dict) for item in rows):
        return [document]

    # 4️⃣ Context = document minus row_source
    context = remove_by_path(document, row_source)

    # 5️⃣ Merge context into each row
    merged_rows = []
    for item in rows:
        merged = {
            **context,
            **item
        }
        merged_rows.append(merged)

    return merged_rows

# DISCOVER SCHEMA

from typing import Set


def discover_schema(
    rows: List[Dict[str, Any]],
    *,
    max_depth: int = 2
) -> List[str]:
    """
    Returns a sorted list of column names across all rows.
    """
    columns: Set[str] = set()

    for row in rows:
        flat = flatten(row, max_depth=max_depth)
        columns.update(flat.keys())

    return sorted(columns)


# PROJECT ROWS
def project_rows(
    rows: List[Dict[str, Any]],
    columns: List[str],
    *,
    max_depth: int = 2
) -> List[Dict[str, Any]]:
    """
    Returns rows projected into the final column schema.
    """
    table = []

    for row in rows:
        flat = flatten(row, max_depth=max_depth)
        projected = {col: flat.get(col) for col in columns}
        table.append(projected)

    return table


# FILTER BY APPROVAL STATUS
from typing import List, Dict


def filter_records_by_approval(
    records: List[Dict],
    *,
    mode: str = "all"  # "approved", "not_approved", "all"
) -> List[Dict]:
    if mode == "all":
        return records
    
    mode_dict = {
        "approved": True,
        "not_approved": False
    }
    
    mode = mode_dict[mode]

    return [
        r for r in records
        if r.get("status") == mode
    ]


def enforce_export_policy(records: List[Dict]) -> List[Dict]:
    return [
        r for r in records
        if r.get("status") == True
    ]


# DETETCT ARRAY PATHS

def discover_array_paths(
    obj,
    *,
    prefix="",
    max_depth=3,
    depth=0
):
    paths = []

    if depth > max_depth:
        return paths

    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            paths.extend(
                discover_array_paths(
                    v,
                    prefix=path,
                    depth=depth + 1,
                    max_depth=max_depth
                )
            )

    elif isinstance(obj, list):
        # Only consider this list itself
        if obj and all(isinstance(i, dict) for i in obj):
            paths.append(prefix)

        # ❗ Do NOT recurse into list items
        return paths

    return paths


def find_array_of_objects_paths(obj, prefix=""):
    paths = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            new_prefix = f"{prefix}.{key}" if prefix else key
            paths.extend(find_array_of_objects_paths(value, new_prefix))

    elif isinstance(obj, list):
        if obj and all(isinstance(item, dict) for item in obj):
            paths.append(prefix)

        # We do NOT recurse into list items further
        # to avoid deep ambiguous nesting

    return paths

# SHOW/HIDE COLUMNS

def apply_column_visibility(
    columns: List[str],
    visible_columns: List[str]
) -> List[str]:
    visible_set = set(visible_columns)
    return [c for c in columns if c in visible_set]


# PAGINATE TABLE

def paginate_table(table: list, page: int = 1, page_size: int = 50):
    """
    Returns a slice of the table and total row count.
    """
    total = len(table)
    start = (page - 1) * page_size
    end = start + page_size
    return table[start:end], total
