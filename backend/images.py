from PIL import ImageOps


def normalize_upload(source, orientation=None):
    """Bake EXIF/explicit capture orientation into pixels, once, before any model."""
    embedded=source.getexif().get(274,1)
    if embedded not in range(1,9):
        embedded=1
    effective=embedded if embedded!=1 else orientation or 1
    if effective not in range(1,9):
        raise ValueError('Image orientation must be an EXIF value from 1 to 8')
    image=source.copy()
    image.getexif()[274]=effective
    image=ImageOps.exif_transpose(image).convert('RGB')
    image.info.clear()
    return image,dict(embedded_orientation=embedded,capture_orientation=orientation,
                      applied_orientation=effective,source_size=list(source.size),
                      normalized_size=list(image.size),pixels_normalized=True)
