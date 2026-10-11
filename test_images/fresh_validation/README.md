# Fresh V2 Validation Photos

Please take three NEW pairs (six photos) using a different object arrangement. The previous seven images are development data and cannot be reused as validation.

Include laptop, silver drink can, black earbud case and white mouse as distinct clearly visible objects, with separation to avoid occlusion. Use consistent lighting and 1x rear camera. Keep the whole inspection area and all tracked objects inside the frame. Do not deliberately change lighting, zoom or object orientation in this first validation. Record your exact actions with file names.

1. `unchanged/before.jpg`, `unchanged/after.jpg`: do not move any object; take consecutive photos with ordinary handheld variation, not copies of the same file.
2. `camera_only/before.jpg`, `camera_only/after.jpg`: move the camera sideways approximately 20% of the scene width without moving any physical object. Keep every tracked object visible. This must be a clean camera-only control, with no simultaneous additions/removals.
3. `object_changes/before.jpg`, `object_changes/after.jpg`: support the camera in a fixed position. Keep the laptop/earbud case/white mouse unchanged; move the silver can sideways by about 20% of frame width, remove a separate book, and add a black fabric item. Do not occlude other objects with the fabric. Tell us exactly what moved/was removed/was added.

Root path: `/Users/yiyao.ding/Desktop/比赛/fielddelta/test_images/fresh_validation/`.

HEIC originals can instead be supplied with an unambiguous pair mapping; conversion preserves originals. Prefer genuine JPEG for direct processing. The site inspection ROI and intended baseline objects must be declared before evaluating predictions. Model prompts and settings remain frozen for the initial validation report; tuning afterward must be separately labeled.
