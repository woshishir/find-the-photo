# v0.3 Manual Evaluation Sheet

Automated tests verify the mechanics; real photographs must verify the taste. Use images you own or have permission to process. Do not tune the skill after a single photograph—record patterns across the set first.

## Test set

Use at least 12 varied sources:

- 3 cluttered portraits or full-body snapshots;
- 2 interiors or tabletop scenes;
- 2 street or architecture images;
- 2 landscapes or travel snapshots;
- 1 image whose best photograph is a small detail;
- 1 weak image that crop alone probably cannot save;
- 1 vertical phone photo containing EXIF orientation.

Include at least two JPG/JPEG files, two PNG files, and two WebP files.

## Score each delivered crop

| Field | Scale |
| --- | --- |
| Standalone photograph | 1–5 |
| Composition feels intentional | 1–5 |
| Clean, deliberate edges | 1–5 |
| Clutter reduction / hierarchy | 1–5 |
| Surprise or visual interest | 1–5 |
| Would you actually keep/post it? | Yes / No |
| Correct role label | Yes / No |
| Raw crop exactness | Pass / Fail |
| Processing fully disclosed | Pass / Fail / Not processed |
| Same aspect ratio as source | Pass / Fail |
| Processing was necessary | Yes / No / Not processed |
| Raw shown before processed | Pass / Fail / Not processed |
| Processed detail looks natural | Pass / Fail / Not processed |
| White balance remains believable | Pass / Fail / Not processed |
| Geometry / inpaint artifacts | None / Describe |
| Notes | Short free text |

Also record whether the one output is genuinely different from the source. A smaller copy of the original, even if attractive, fails the Discovery Gate.

## v0.3 acceptance target

- At least 70% of sources judged salvageable produce one `unexpected` crop you would keep or post.
- At least 80% of `unexpected` outputs rated as correctly labeled feel non-obvious, not merely tighter.
- Zero final outputs at or above 50% of source area.
- Zero format, orientation, overwrite, stretching, undisclosed-processing, or source-aspect failures.
- Every sub-20% delivered crop includes raw then processed, with the processed file at source dimensions.
- Every correction stays within the documented limits and leaves no visible artifact at normal viewing size.
- No processed companion invents an object, reconstructs hidden anatomy, or alters protected text, plates, or defining subject edges.
- Weak sources may return zero results without penalty when the explanation is honest.

## Iteration rule

Tag each failure as `proposal`, `critic`, `discovery-gate`, `selection`, `coordinate`, `rendering`, `recovery`, `geometry`, `inpaint`, `white-balance`, or `unnecessary-processing`. Adjust the narrowest responsible instruction or test. Keep the source, raw crop, processed crop, and run folder so the change can be compared against the same case.
