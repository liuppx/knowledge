"""Frozen public-record identifiers for the ontology V1 proxy pilot.

The records themselves remain owned and served by their official sources.  The
pilot fixes identifiers instead of committing copies, then records response
hashes in its report so source corrections become visible.
"""

from __future__ import annotations


USA_AWARD_IDS = (
    "CONT_AWD_ZN31_9700_W91QUZ06D0004_9700",
    "CONT_AWD_ZL54_9700_H9222210D0019_9700",
    "CONT_AWD_ZL06_9700_N0024412D0014_9700",
    "CONT_AWD_Z594_9700_N0001914D0001_9700",
    "CONT_AWD_Z550_9700_N0001913D0007_9700",
    "CONT_AWD_Z506_9700_N0001914D0001_9700",
    "CONT_AWD_Z503_9700_N0001914D0001_9700",
    "CONT_AWD_Z18E_9700_SPRPA113G001X_9700",
    "CONT_AWD_XT06_9700_N0001908G0002_9700",
    "CONT_AWD_Z35J_9700_SPRPA113G001X_9700",
)


TED_NOTICE_PAIRS = (
    ("0d4b759d-089c-4b8b-97f0-91276cb03ce6", "ba7a1185-4e7d-4c71-a1bb-6f2099127aa5"),
    ("a6c20ce1-ae27-4f25-b057-51bc2260f138", "65c8f84b-9668-4c70-802c-4ca3d746e1b9"),
    ("d81443ac-81c7-4c72-810e-c7cae7fae555", "5c2991e9-727c-4495-8dae-c19d936aa7fd"),
    ("e8c81c20-70cf-44c8-874d-88a2f2912d06", "d2184597-3d69-40fc-8d06-7ba2af670ad9"),
    ("c39bcf5c-aeba-4cbe-bb55-c3a878749e21", "bc54ba3b-2f0a-4f82-98dd-a6e81fb270bb"),
    ("8d6b78b3-5b24-4a57-a222-c093b99e85b4", "f6202b9a-3877-453f-a24e-f6a6c0af7361"),
    ("b3ed714a-3491-4978-9e27-e823ad131f98", "b732dc34-205b-4b01-b39d-9ed0b608491e"),
    ("cdaea9b9-31d0-4ee3-b4c4-ed1f9182a324", "9c62249e-6449-490f-93f6-69f79694e225"),
    ("a511f820-3f57-4462-bf25-b6ab0f081ba3", "c0d1d32a-b519-44d2-9d7d-c0fd8f918351"),
    ("1354c082-c7c2-4b6f-86ed-5f0a2a6fb797", "786a4d57-66fb-42ee-975d-a31f754c251a"),
)


GLEIF_LEIS = (
    "WHKXQACZ14C5XRO8LW03",  # HP INC. / Hewlett-Packard Company
    "I07WOS4YJ0N7YRFE7309",  # RTX / Raytheon Technologies / United Technologies
    "5493006ZCRFWKF6B1K26",  # Warner Bros. Discovery / Discovery
    "549300B2FTG34FILDR98",  # Uber Technologies / Ubercab
    "894500TOVTJDJJ6WSU81",  # Silver X Mining / Oro X Mining
)


EXPECTED_NORMALIZED_SOURCE_SHA256 = "78bb51d6764f6988e2ee2c12f10504cbeafa1d8f1085bfb26d85012e0ef366f0"
TOP_K = 6
TOP_K_SENSITIVITY = (6, 10, 15, 20)
