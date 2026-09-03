# The measurement instrument

What a measured row IS, how that definition is installed into a revision being
measured, and what the same tree's own parallel execution costs.

`contract.py` is the row contract every result carries, so a comparator can
refuse two arms that did not measure the same thing rather than averaging them.

`copy.py` installs the corrected protocol into a revision's checkout and
rewrites the one name a public rename moved. Each copy keeps only its native API
reference, and no `src` tree is touched.

`health.py` answers a different question from the A/B: not "is head slower than
base" but "does this tree's AUTO policy beat its own single worker". A
pre-existing parallel loss and a new regression are different facts, and mixing
them is how one gets read as the other.
