"""Minimal SCIP binary (protobuf) parser.

Parses ``.scip`` index files produced by SCIP indexers (scip-python,
scip-typescript, scip-java …) using raw protobuf wire-format decoding.
No generated code or external proto-compilation step is required.

SCIP proto reference:
  https://github.com/sourcegraph/scip/blob/main/scip.proto

Wire-format field mapping used here
====================================
Index       field 3 → repeated Document documents
            field 4 → repeated SymbolInformation external_symbols

Document    field 1 → string relative_path
            field 2 → repeated Occurrence occurrences
            field 3 → repeated SymbolInformation symbols
            field 4 → string language

Occurrence  field 1 → repeated int32 range (packed)
            field 2 → string symbol
            field 3 → int32 symbol_roles  (bitmask: 1=Definition, 4=WriteAccess)

SymbolInformation
            field 1 → string symbol
            field 3 → repeated Relationship relationships
            field 8 → SymbolKind (enum / int32)

Relationship
            field 1 → string symbol
            field 2 → bool is_reference
            field 3 → bool is_implementation
            field 4 → bool is_type_definition
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Protobuf wire-format helpers
# ---------------------------------------------------------------------------

_WIRE_VARINT = 0
_WIRE_64BIT = 1
_WIRE_LEN = 2
_WIRE_32BIT = 5


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    """Decode a base-128 varint starting at *pos*.

    Returns:
        Tuple of (decoded_value, new_position).
    """
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


def _parse_message(buf: bytes) -> dict[int, list]:
    """Parse a protobuf message into ``{field_number: [raw_values]}`` dict.

    Wire-type 0 (varint) values are stored as ``int``.
    Wire-type 2 (length-delimited) values are stored as ``bytes``.
    Other wire types (64-bit, 32-bit) are skipped.

    Truncated or malformed fields are silently skipped so that partial data
    (e.g. very large index files near buffer boundaries) does not cause crashes.
    """
    fields: dict[int, list] = {}
    pos = 0
    n = len(buf)
    while pos < n:
        try:
            tag, pos = _read_varint(buf, pos)
        except IndexError:
            break
        fn = tag >> 3
        wt = tag & 0x7
        try:
            if wt == _WIRE_VARINT:
                val, pos = _read_varint(buf, pos)
                fields.setdefault(fn, []).append(val)
            elif wt == _WIRE_64BIT:
                if pos + 8 > n:
                    break
                pos += 8
            elif wt == _WIRE_LEN:
                length, pos = _read_varint(buf, pos)
                if pos + length > n:
                    break
                fields.setdefault(fn, []).append(buf[pos : pos + length])
                pos += length
            elif wt == _WIRE_32BIT:
                if pos + 4 > n:
                    break
                pos += 4
            else:
                # Unknown wire type — stop to avoid misalignment.
                break
        except IndexError:
            break
    return fields


def _str(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _packed_int32(data: bytes) -> list[int]:
    """Decode a packed-varint byte string into a list of integers."""
    values: list[int] = []
    pos = 0
    while pos < len(data):
        v, pos = _read_varint(data, pos)
        values.append(v)
    return values


# ---------------------------------------------------------------------------
# SymbolKind enum (subset used for Neo4j node labels / display)
# ---------------------------------------------------------------------------

SYMBOL_KINDS: dict[int, str] = {
    0: "Unknown",
    1: "AbstractMethod",
    2: "Accessor",
    8: "Class",
    9: "Constant",
    10: "Constructor",
    11: "Enum",
    12: "EnumMember",
    15: "Field",
    16: "File",
    17: "Function",
    21: "Interface",
    24: "Local",
    26: "Method",
    28: "Module",
    29: "Namespace",
    34: "Package",
    35: "Parameter",
    36: "Property",
    44: "StaticField",
    45: "StaticMethod",
    49: "Struct",
    52: "Trait",
    53: "Type",
    54: "TypeAlias",
    59: "Variable",
}

# SymbolRole bitmask values
ROLE_DEFINITION = 1
ROLE_IMPORT = 2
ROLE_WRITE_ACCESS = 4
ROLE_READ_ACCESS = 8


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Relationship:
    symbol: str
    is_reference: bool = False
    is_implementation: bool = False
    is_type_definition: bool = False


@dataclass
class SymbolInfo:
    symbol: str
    kind: int = 0
    relationships: list[Relationship] = field(default_factory=list)

    @property
    def kind_name(self) -> str:
        return SYMBOL_KINDS.get(self.kind, "Unknown")


@dataclass
class Occurrence:
    symbol: str
    range: list[int] = field(default_factory=list)
    symbol_roles: int = 0

    @property
    def is_definition(self) -> bool:
        return bool(self.symbol_roles & ROLE_DEFINITION)


@dataclass
class Document:
    relative_path: str
    language: str = ""
    occurrences: list[Occurrence] = field(default_factory=list)
    symbols: list[SymbolInfo] = field(default_factory=list)


@dataclass
class ScipIndex:
    documents: list[Document] = field(default_factory=list)
    external_symbols: list[SymbolInfo] = field(default_factory=list)

    @property
    def stats(self) -> dict[str, int]:
        total_syms = sum(len(d.symbols) for d in self.documents)
        total_occs = sum(len(d.occurrences) for d in self.documents)
        total_rels = sum(
            len(s.relationships) for d in self.documents for s in d.symbols
        )
        return {
            "documents": len(self.documents),
            "symbols": total_syms,
            "occurrences": total_occs,
            "relationships": total_rels,
            "external_symbols": len(self.external_symbols),
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_relationship(data: bytes) -> Relationship:
    f = _parse_message(data)
    sym_raw = f.get(1, [b""])[0]
    return Relationship(
        symbol=_str(sym_raw) if isinstance(sym_raw, bytes) else "",
        is_reference=bool(f.get(2, [0])[0]),
        is_implementation=bool(f.get(3, [0])[0]),
        is_type_definition=bool(f.get(4, [0])[0]),
    )


def _parse_symbol_info(data: bytes) -> SymbolInfo:
    f = _parse_message(data)
    sym_raw = f.get(1, [b""])[0]
    return SymbolInfo(
        symbol=_str(sym_raw) if isinstance(sym_raw, bytes) else "",
        kind=f.get(8, [0])[0],
        relationships=[
            _parse_relationship(r) for r in f.get(3, []) if isinstance(r, bytes)
        ],
    )


def _parse_occurrence(data: bytes) -> Occurrence:
    f = _parse_message(data)
    # range is packed repeated int32 → stored as a single bytes object
    range_entries = f.get(1, [])
    if range_entries and isinstance(range_entries[0], bytes):
        rng = _packed_int32(range_entries[0])
    else:
        rng = [int(v) for v in range_entries]

    sym_raw = f.get(2, [b""])[0]
    return Occurrence(
        range=rng,
        symbol=_str(sym_raw) if isinstance(sym_raw, bytes) else "",
        symbol_roles=f.get(3, [0])[0],
    )


def _parse_document(data: bytes, *, old_layout: bool = False) -> Document:
    f = _parse_message(data)
    path_raw = f.get(1, [b""])[0]
    lang_raw = f.get(4, [b""])[0]

    if isinstance(lang_raw, bytes) and lang_raw:
        language = _str(lang_raw)
    elif old_layout:
        # Old layout (scip-java) omits the language field; infer from path.
        path_str = _str(path_raw) if isinstance(path_raw, bytes) else ""
        language = _infer_language(path_str)
    else:
        language = ""

    return Document(
        relative_path=_str(path_raw) if isinstance(path_raw, bytes) else "",
        language=language,
        occurrences=[
            _parse_occurrence(o) for o in f.get(2, []) if isinstance(o, bytes)
        ],
        symbols=[
            _parse_symbol_info(s) for s in f.get(3, []) if isinstance(s, bytes)
        ],
    )


def _infer_language(path: str) -> str:
    """Guess language from file extension when the proto field is absent."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "java": "java", "kt": "kotlin", "kts": "kotlin",
        "py": "python", "ts": "typescript", "tsx": "typescript",
        "js": "javascript", "jsx": "javascript",
        "go": "go", "rs": "rust", "rb": "ruby",
    }.get(ext, ext or "unknown")


def parse_scip_file(path: str | Path) -> ScipIndex:
    """Parse a SCIP index (``.scip``) binary file into a :class:`ScipIndex`.

    Handles two proto layouts emitted by different SCIP indexer versions:

    **New layout** (scip-python, scip-typescript, recent versions):
      - ``Index.documents``        = field 3
      - ``Index.external_symbols`` = field 4
      - ``Document.language``      = field 4

    **Old layout** (scip-java and other older indexers):
      - ``Index.documents``        = field 2
      - ``Index.external_symbols`` = field 3
      - ``Document.language``      = absent (defaults to ``"java"``)

    Args:
        path: Path to the ``.scip`` file produced by a SCIP indexer.

    Returns:
        Parsed :class:`ScipIndex` with all documents, symbols, and occurrences.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError:        If the file is not a valid protobuf / SCIP binary.
    """
    data = Path(path).read_bytes()
    if not data:
        raise ValueError(f"SCIP file is empty: {path}")

    f = _parse_message(data)

    # Detect proto layout: new indexers put documents at field 3;
    # older ones (e.g. scip-java) put them at field 2.
    if f.get(3):
        doc_entries = f.get(3, [])
        ext_entries = f.get(4, [])
        _old_layout = False
    else:
        doc_entries = f.get(2, [])
        ext_entries = f.get(3, [])
        _old_layout = True

    documents = [_parse_document(d, old_layout=_old_layout) for d in doc_entries if isinstance(d, bytes)]

    return ScipIndex(
        documents=documents,
        external_symbols=[
            _parse_symbol_info(s) for s in ext_entries if isinstance(s, bytes)
        ],
    )
