"""Real photos for the film (film/assets/photo_*.jpg, Pexels licence, see assets/sources.json): resized to 2560 px
wide for the page, into film/assets/web/. render.cjs puts the ones that exist into the film.
Run: python film/prep_media.py
"""
import os

from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "assets")
DST = os.path.join(SRC, "web")
os.makedirs(DST, exist_ok=True)
for f in sorted(os.listdir(SRC)):
    if f.startswith("photo_") and f.endswith(".jpg"):
        im = ImageOps.exif_transpose(Image.open(os.path.join(SRC, f))).convert("RGB")
        w = 2560
        if im.width > w:
            im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
        im.save(os.path.join(DST, f), quality=90)
        print(f, im.size)
