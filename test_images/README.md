# Please Capture Two Real Photo Pairs

Use the rear camera at 1x. Put the phone on a stable support and do not move it between photos. Keep orientation, zoom, lighting and framing unchanged. Use normal JPEG photos (iPhone Camera settings > Formats > Most Compatible), not HEIC renamed as JPEG.

## Scene 01: One Added, One Removed, One Moved

Use a well-lit desk with a clearly visible laptop, bottle, cup, and book. Keep objects separate, mostly unobstructed, and large enough to inspect (roughly 100 pixels or more across in a 1200-pixel-wide photo). Avoid tiny objects, identical cups/bottles, mirrors and hands in frame.

1. Capture the baseline with laptop, bottle and cup present. Save `scene_01/before.jpg`.
2. Leave the laptop unchanged.
3. Remove the cup entirely from the frame.
4. Move the same bottle sideways by roughly 20% of the image width. Keep its orientation similar.
5. Add a clearly visible book in an otherwise empty spot.
6. Capture the second photo from exactly the same supported phone position. Save `scene_01/after.jpg`.

Expected physical truth: cup REMOVED, bottle MOVED, book ADDED, laptop UNCHANGED. This is a validation target, not a generated result. If the detector misses an object, report that failure rather than adjusting the truth.

## Scene 02: No-Change Control

Use a different desk arrangement with a laptop, bottle and cup, keeping each visible and separated. Capture two consecutive photos without moving either the phone or anything in the scene.

Save `scene_02/before.jpg` and `scene_02/after.jpg`. Expected physical truth: all detected objects UNCHANGED; zero added/removed/moved events.

## Exact Directory

`/Users/yiyao.ding/Desktop/比赛/fielddelta/test_images/`

Do not create placeholder photos. The folders are prepared and empty until real photos are supplied. Tell the agent once the four files are saved; mention any deviation from the requested physical changes.
