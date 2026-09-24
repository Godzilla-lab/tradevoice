# Real handwriting test photos

Printed test images are easy. **Handwriting is the real test.** For each page:

1. Write a notebook page by hand like a real trader would (shorthand, "bal", "cr", crossed-out lines), in one language.
2. Photograph it with a phone (flat page, daylight). Save as `yoruba_1.jpg`, `hausa_1.jpg`, `igbo_1.jpg`, `pidgin_1.jpg`,
   `english_1.jpg`. The part before `_` is the language shown in the results.
3. Type exactly what is written, with all tone marks, into a text file with the same name: `yoruba_1.txt`.
4. Run `python eval/lang_check.py --images-only`. Your photos are scored alongside the printed tests.

Aim for at least 2 pages per language, written by different people. Use fake names only.
