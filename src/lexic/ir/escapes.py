"""EscapeCodec — the flavour's emit-side spelling of canonical text, on the spine.

A flavour's escape codec is its **spell refinement over ``IrUnicode``**: where
the neutral ``IrUnicode`` encoding spells an ordinal as the raw glyph
(``IrChr.eval`` = ``chr``), the codec spells canonical text as *escaped* source
in the flavour's syntax. It is emit-only — the parse side decodes escapes
structurally in the reductions, so the codec has no resolve/decode half.

It is an :class:`~lexic.ir.base.IrNamedTuple` record (the
:class:`~lexic.ir.encoding.IrTokenizer` precedent — an ``IrSelf`` on the IR
spine, IR-native data, ``_child_attrs = ()``), **not** an
:class:`~lexic.ir.encoding.IrEncoding`: the encoding contract
(``universe``/``resolve``/``spell``) does not fit an emit-only spelling policy.
Its five fields ARE the five escape tables, IR-native throughout — the schema
is fixed, so the record tier names it rather than burying it in one keyed map
(a manifest's ``escapes`` section is lowered onto the fields by the notation
loader, which raises on an unknown or missing table). The
encode/encode_point/spellable algorithms are intrinsic and are read via the
dispatcher's ``escapes`` field by
:class:`~lexic.ir.flavour.IrEscape` / ``IrEscapePoint`` / ``IrSpellable``.
"""

from __future__ import annotations

from typing import ClassVar

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrInt, IrNamedTuple, IrStr, IrTuple
from lexic.ir.mapping import IrMap


class EscapeCodec(IrNamedTuple[IrMap, IrTuple, IrMap, IrTuple, IrTuple]):
    """Emit-side encode/encode_point/spellable over five IR-native tables.

    The five tables are the record's five FIELDS, not entries in one map: the
    schema is fixed and known, so the record tier names it (a map would make
    every read re-narrow, and a misspelled table would read empty instead of
    raising).

    :ivar short: ``IrMap[IrStr → IrStr]`` — source follow-char → canonical char.
    :ivar hexes: ``IrTuple`` of ``(tag, width)`` dyads, narrowest first.
    :ivar class_short: ``IrMap[IrInt → IrStr]`` — code point → class spelling.
    :ivar class_meta: ``IrTuple`` of ``IrStr`` — backslash-escaped class chars.
    :ivar quote_safe: ``IrTuple`` of ``(lo, hi)`` spellable code-point ranges.

    Children: none walked — every field is codec data (``_child_attrs = ()``).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    short: IrMap = IrMap()
    hexes: IrTuple = IrTuple()
    class_short: IrMap = IrMap()
    class_meta: IrTuple = IrTuple()
    quote_safe: IrTuple = IrTuple()

    @staticmethod
    def from_tables(
        *,
        short: dict[str, str] | None = None,
        hexes: tuple[tuple[str, int], ...] = (),
        class_short: dict[int, str] | None = None,
        class_meta: str = "",
        quote_safe: tuple[tuple[int, int], ...] = (),
    ) -> EscapeCodec:
        """Build a codec from plain-Python tables (the authoring convenience).

        Each table is lifted to its IR-native form; omitted tables are empty.
        The flavour-source counterpart of the manifest loader's record
        construction. A typo'd keyword is a native ``TypeError`` (the signature
        is explicit), so no table is ever silently dropped.

        :param short: source follow-char → canonical char.
        :param hexes: ``(tag, width)`` hex-escape forms, narrowest first.
        :param class_short: code point → bracket-class short spelling.
        :param class_meta: characters backslash-escaped inside a class.
        :param quote_safe: ``(lo, hi)`` code-point ranges for the quoted form.
        :returns: The escape codec record.
        """
        return EscapeCodec(
            IrMap(*(IrTuple(IrStr(k), IrStr(v)) for k, v in (short or {}).items())),
            IrTuple(*(IrTuple(IrStr(t), IrInt(w)) for t, w in hexes)),
            IrMap(
                *(IrTuple(IrInt(k), IrStr(v)) for k, v in (class_short or {}).items())
            ),
            IrTuple(*(IrStr(c) for c in class_meta)),
            IrTuple(*(IrTuple(IrInt(lo), IrInt(hi)) for lo, hi in quote_safe)),
        )

    def encode(self, value: str) -> str:
        """Encode canonical Python into the flavour's escape syntax.

        Inverts ``short`` (canonical → ``\\follow``). ``short`` is an ``IrMap``,
        whose entries are ordered by ``repr`` of the source key — so if two
        source chars ever decoded to the *same* canonical char (no supported
        flavour does), the repr-last source would win the inversion, not the
        author-declared one. A colliding-target ``short`` table would need an
        order-preserving representation.

        :param value: The canonical literal text.
        :returns: The source-form text with each ``short`` char backslash-escaped.
        """
        table = {str(canon): "\\" + str(src) for src, canon in self.short.items()}
        return "".join(table.get(c, c) for c in value)

    def encode_point(self, cp: int) -> str:
        """Spell one code point for safe use inside a bracket class.

        The emit-side inverse of the class-escape reduce rules: the
        ``class-short`` spelling first, a backslash before a ``class-meta``
        character, the bare glyph when printable, then the narrowest ``hex`` form
        that fits.

        :param cp: The code point to spell.
        :returns: The class-safe member text.
        :raises UnsupportedConstructError: If no hex form is wide enough.
        """
        short = self.class_short.get(IrInt(cp))
        if short is not None:
            return str(short)
        ch = chr(cp)
        if any(ch == str(meta) for meta in self.class_meta):
            return "\\" + ch
        if ch.isprintable():
            return ch
        for pair in self.hexes:
            tag, width = str(pair[0]), int(pair[1])
            if cp < 16**width:
                return f"\\{tag}{cp:0{width}x}"
        raise UnsupportedConstructError(
            f"{type(self).__name__}: no hex escape fits code point {cp:#x}"
        )

    def spellable(self, text: str) -> bool:
        """Whether every character fits the quoted literal form.

        :param text: The candidate literal text.
        :returns: True when each code point falls in a ``quote_safe`` range.
        """
        ranges = [(int(pair[0]), int(pair[1])) for pair in self.quote_safe]
        return all(any(lo <= ord(c) <= hi for lo, hi in ranges) for c in text)
