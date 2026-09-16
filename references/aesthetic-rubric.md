# Aesthetic Rubric

## Proposer recipe

Use this editorial brief:

> Find one photograph hidden inside this image. Treat the original as raw visual material, not a frame that must be preserved. Look for a local scene, gesture, texture, reflection, or spatial relationship that becomes an independent photograph when isolated. Propose bold, source-aspect crops that occupy less than half of the source area and feel materially different from the original. Do not generate or repair anything during proposal.

Create 6–10 candidates. Every candidate has role `unexpected`; do not spend candidates on safe or editorial versions of the full composition. Aim for a decisive local fragment rather than the largest attractive crop. Useful targets include:

- two figures whose relationship creates a small story;
- water, reflections, light, shadow, or surface texture as the subject;
- railings, shorelines, roads, architecture, or branches that create strong diagonals and layers;
- a cropped gesture or object that changes meaning outside the original context.

Candidate area must be strictly below 50% after rendering. Many good discoveries will be in the 15–35% range, but do not force a tiny crop when the source cannot support one at the minimum resolution.

Candidates must differ in visual idea, not merely shift a nearly identical box by a few pixels. Preserve necessary breathing room around gazes, gestures, moving subjects, and strong lines. A close crop is useful only when the resulting fragment feels intentional.

Before rendering, discard any proposal that:

- depends on content outside its boundary to make sense;
- leaves background clutter that competes with the subject;
- cuts anatomy, typography, or dominant geometry indecisively;
- is essentially a duplicate of another candidate;
- leaves the main subject and original spatial story mostly intact;
- is only a gentle border trim or a smaller copy of the original;
- occupies 50% or more of the source area;
- changes the source aspect ratio (`right - left` must equal `bottom - top` within `0.001`);
- will fail the 512 px minimum short edge.

## Blind critic prompt

Give the critic only the rendered candidate PNGs with neutral filenames and this text:

> You are a strict photography editor. Judge every crop as an independent photograph. You have not seen the source and do not need to infer it. Ask: “If this were the only image I saw, would I keep it?” Reward clear local intent, visual hierarchy, controlled edges, useful negative space, tension, rhythm, and memorable detail. Penalize generic centering, residual clutter, timid framing, accidental cutoffs, weak focal points, and near-duplicate ideas. Prefer a fragment with its own story or abstraction over a complete-looking scene. Do not reward a crop merely because it may be better than an unseen original.

Score every candidate from 0–5 on:

| Criterion | Question |
| --- | --- |
| Standalone strength | Does it work without context from the source? |
| Composition | Does the frame feel deliberate and balanced or productively tense? |
| Edge control | Are all four edges intentional, especially around anatomy, text, and geometry? |
| Hierarchy | Is attention directed clearly without competing clutter? |
| Visual interest | Is there enough specificity, surprise, mood, or rhythm to keep it? |

Return only a compact JSON array:

```json
[
  {
    "id": "crop-01",
    "scores": {
      "standalone": 4,
      "composition": 5,
      "edges": 4,
      "hierarchy": 4,
      "interest": 4
    },
    "total": 21,
    "fatal_issue": null,
    "verdict": "keep",
    "reason": "The off-axis figure and empty wall create controlled tension."
  }
]
```

## Discovery Gate

After the blind pass, show only the source-oriented preview and the blind keepers to a fresh comparison pass. This pass may see the source; it exists to catch the failure the blind pass cannot: a crop that is independently pleasant but too similar to the original.

Use this prompt:

> Compare each candidate with the source. Keep only a photograph that feels discovered, not resized. Reject it if the original subject, horizon, spatial layout, or visual story remains mostly intact; if it only trims empty borders; or if a viewer would describe it as “the same photo, just closer.” Reward a new focal subject, local narrative, abstraction, strong line or layer, or a meaningful change in scale and context. A candidate must still work without the source and must occupy less than 50% of the source area.

Score each blind keeper from 0–5 on:

| Criterion | Question |
| --- | --- |
| Transformation | Does it materially change what the photograph is about? |
| Independence | Would it make sense without the source? |
| Specificity | Is there a memorable local detail, relation, texture, or rhythm? |

A candidate passes the Discovery Gate only with `transformation >= 4`, `independence >= 4`, and no near-original or edge failure. Rank passing candidates by transformation first, then independence and blind total. Select exactly one.

## Selection gate

A candidate qualifies in the blind pass only when:

- `total >= 19/25`;
- `standalone >= 4`;
- `edges >= 3`;
- `fatal_issue` is `null`; and
- it is not compositionally redundant with a stronger winner.

The blind score is necessary but not sufficient. The final selection must also pass the Discovery Gate and the renderer's strict `<50%` area check. If no candidate passes both gates, select none.

## Post-selection correction decision

Judge corrections only after selecting and re-rendering final raw crops. Process a crop when its measured area is below 20%, or when the raw final has a clearly visible tilt, mild perspective error, or tiny removable distraction. Correction is not a second chance for a weak composition.

Keep the raw crop and reject any processed companion that introduces halos, color casts, clipped highlights, warped geometry, repeated texture, false detail, or visible inpainting. Read [the correction schema](correction-schema.md) before proposing a correction manifest.

## Calibration notes from accepted examples

When a source contains water, sunset light, a promenade, railings, people, or architecture, test a small local story before considering a broad scenic crop. Strong examples isolate a pair of people against reflected water, a diagonal waterfront barrier with figures, or water and pavement as an abstract banded composition. The common quality is not the location; it is that the crop changes the subject and reads as a complete image on its own.
