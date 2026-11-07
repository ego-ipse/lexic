"""The spine group — see README.md."""

SURFACE: dict[str, str] = {
    "BIND_MODES": "lexic.ir.spine.bind",
    "IrBind": "lexic.ir.spine.bind",
    "Borg": "lexic.ir.spine.meta",
    "IrMeta": "lexic.ir.spine.meta",
    "IrSingleton": "lexic.ir.spine.meta",
    "Singleton": "lexic.ir.spine.meta",
    "Bound": "lexic.ir.spine.records",
    "Field": "lexic.ir.spine.records",
    "IrCachingTuple": "lexic.ir.spine.records",
    "IrNamedTuple": "lexic.ir.spine.records",
    "IrSeq": "lexic.ir.spine.records",
    "IrTuple": "lexic.ir.spine.records",
    "is_plain_tuple": "lexic.ir.spine.records",
    "IrChr": "lexic.ir.spine.scalars",
    "IrInt": "lexic.ir.spine.scalars",
    "IrScalar": "lexic.ir.spine.scalars",
    "IrStr": "lexic.ir.spine.scalars",
    "IrAtom": "lexic.ir.spine.spine",
    "IrLambda": "lexic.ir.spine.spine",
    "IrLeaf": "lexic.ir.spine.spine",
    "IrNode": "lexic.ir.spine.spine",
    "IrNone": "lexic.ir.spine.spine",
    "IrNoneType": "lexic.ir.spine.spine",
}
"""Every name this group puts on the ``lexic.ir`` façade, and the module that
defines it. The façade's lazy lookup reads it, so a name resolves only once
listed here. Data only, as the marker is: every import of a submodule runs it
first."""
