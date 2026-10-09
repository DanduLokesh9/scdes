/* Retired. Its subject was removed, and it has been failing on nothing.
 *
 * This harness drove the project spine strip — `#spineTrack .gate[data-gate]`
 * — clicking gate 4, then 0, then 2, and reporting which one lit up. It was
 * written to catch a real bug, where the highlight tracked the project's own
 * gate instead of the gate you had just clicked.
 *
 * Two things ended it. The strip itself was retired: a bar claiming to show
 * where "the project" is, above a screen about something else, is only ever
 * right while exactly one project exists. Its markup came out of index.html
 * with it, so every run of this file since has died on `btn.disabled` with
 * `btn` null — a failure about absent furniture rather than about behavior.
 *
 * And its premise is now forbidden. It addressed gates by number, which is
 * the one thing the lifecycle spine rules out everywhere in this product: a
 * numbered gate invites a reader to line these seven up against somebody
 * else's staging scheme. There is no version of this file that could be
 * fixed rather than replaced.
 *
 * What replaced it: `tools/check_new_screens.js`. It exercises the tracker on
 * Projects — all seven gates by name, each carrying its state as text as well
 * as by tint — and it fails on any numbered gate form anywhere in the DOM of
 * any screen it can open, which is the check this file was reaching for.
 *
 * See also the note above `renderSpine()` in app/web/assets/app.js, and the
 * one above `api_config` in app/server.py.
 */

console.log(
  "check_spine.js is retired. The spine strip it drove was removed, and it\n" +
  "addressed gates by number, which the spine forbids. The tracker that\n" +
  "replaced it is checked by tools/check_new_screens.js — run that instead.");
process.exit(0);
