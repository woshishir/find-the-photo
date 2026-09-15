# Gentle Correction Schema

Use this schema only after final raw crops have passed blind selection and edge inspection. Corrections are optional; do not create a correction entry when the raw crop is already clean.

## Manifest

```json
{
  "schema_version": "1.0",
  "corrections": [
    {
      "id": "02-unexpected",
      "rotation_degrees": -1.5,
      "perspective_corners": [
        [0.01, 0.02],
        [0.99, 0.01],
        [0.98, 0.99],
        [0.02, 0.98]
      ],
      "inpaint_polygons": [
        [[0.10, 0.10], [0.12, 0.10], [0.12, 0.12], [0.10, 0.12]]
      ]
    }
  ]
}
```

Coordinates are normalized to the raw crop. Corner order is top-left, top-right, bottom-right, bottom-left. Omit an operation when it is unnecessary.

## Hard limits

| Operation | Limit |
| --- | --- |
| Rotation | `-5.0` through `5.0` degrees |
| Perspective | Each corner may move at most `0.08` on either normalized axis from its canonical corner |
| Local inpainting | Combined polygon area must be at most `0.01` of the raw crop |

The script rejects the entire job before output when any numeric limit, ID, point, polygon, or schema field is invalid.

## Semantic exclusions

The visual agent must not place an inpainting mask over:

- a face, body, hand, or other anatomy;
- a license plate or readable text;
- a defining subject contour or recognizable object feature;
- content whose hidden appearance would need to be guessed.

Acceptable masks cover only tiny simple distractions over predictable surroundings, such as sensor dust, a thin wire, or a small edge fragment. If the repair could change the meaning or identity of the photograph, return the raw crop instead.

## Output behavior

A valid correction triggers a processed companion even when the crop occupies at least 20% of the source. The raw crop remains unchanged and is shown first. Correction-only output returns to the raw crop's pixel dimensions; a crop below 20% returns to the oriented source dimensions through Resolution Recovery.

Inspect processed output for warped geometry, repeated texture, halos, color casts, clipped highlights, and inpainting artifacts. Reject the processed companion if any artifact is visible at normal viewing size.
