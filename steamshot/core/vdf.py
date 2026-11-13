"""Parser/serializador mínimo del formato KeyValues de texto de Valve (.vdf/.acf).

Conserva el orden de las claves y escribe con el mismo estilo que el cliente de
Steam (tabuladores), de forma que ``dumps(loads(texto)) == texto`` para los
archivos que genera Steam.
"""
from __future__ import annotations

from ..i18n import tr

_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}


class VDFError(ValueError):
    pass


def _tokens(text: str):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n﻿":
            i += 1
        elif c == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
        elif c in "{}":
            yield c, None
            i += 1
        elif c == '"':
            i += 1
            buf = []
            while True:
                if i >= n:
                    raise VDFError(tr("vdf_unclosed"))
                c = text[i]
                if c == "\\" and i + 1 < n and text[i + 1] in _ESCAPES:
                    buf.append(_ESCAPES[text[i + 1]])
                    i += 2
                elif c == '"':
                    i += 1
                    break
                else:
                    buf.append(c)
                    i += 1
            yield "s", "".join(buf)
        elif c == "[":  # condicionales tipo [$WIN]: se ignoran
            j = text.find("]", i)
            i = n if j < 0 else j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n{}"':
                j += 1
            yield "s", text[i:j]
            i = j


def loads(text: str) -> dict:
    root: dict = {}
    stack = [root]
    key = None
    for kind, val in _tokens(text):
        if kind == "s":
            if key is None:
                key = val
            else:
                stack[-1][key] = val
                key = None
        elif kind == "{":
            if key is None:
                raise VDFError(tr("vdf_brace_key"))
            child: dict = {}
            stack[-1][key] = child
            stack.append(child)
            key = None
        else:  # "}"
            if len(stack) == 1:
                raise VDFError(tr("vdf_brace_open"))
            stack.pop()
    if len(stack) != 1 or key is not None:
        raise VDFError(tr("vdf_incomplete"))
    return root


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def dumps(obj: dict, level: int = 0) -> str:
    out = []
    tab = "\t" * level
    for k, v in obj.items():
        if isinstance(v, dict):
            out.append(f'{tab}"{_esc(k)}"\n{tab}{{\n')
            out.append(dumps(v, level + 1))
            out.append(f"{tab}}}\n")
        else:
            out.append(f'{tab}"{_esc(k)}"\t\t"{_esc(str(v))}"\n')
    return "".join(out)


def load(path) -> dict:
    with open(path, encoding="utf-8", errors="replace") as f:
        return loads(f.read())
