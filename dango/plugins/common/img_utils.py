import itertools

import PIL
import textwrap


def draw_text_outline(draw: PIL.ImageDraw.Draw,
                      location, text, color, outline_color, outline_width, *args, **kwargs):
    """Draw text with outline in the shittiest way possible."""
    # Remember - (0,0) is top left
    from_left, from_top = location
    if outline_width:
        draw.text((from_left + outline_width, from_top), text, *args, fill=outline_color, **kwargs)
        draw.text((from_left - outline_width, from_top), text, *args, fill=outline_color, **kwargs)
        draw.text((from_left, from_top + outline_width), text, *args, fill=outline_color, **kwargs)
        draw.text((from_left, from_top - outline_width), text, *args, fill=outline_color, **kwargs)
        draw.text((from_left + outline_width, from_top - outline_width), text, *args, fill=outline_color, **kwargs)
        draw.text((from_left - outline_width, from_top + outline_width), text, *args, fill=outline_color, **kwargs)
        draw.text((from_left + outline_width, from_top + outline_width), text, *args, fill=outline_color, **kwargs)
        draw.text((from_left - outline_width, from_top - outline_width), text, *args, fill=outline_color, **kwargs)
    draw.text((from_left, from_top), text, *args, fill=color, **kwargs)


def draw_text_dropshadow(draw: PIL.ImageDraw.Draw,
                         location, text, color, shadow_color, shadow_offset, *args, **kwargs):
    """Draw text with outline in the shittiest way possible."""
    # Remember - (0,0) is top left
    from_left, from_top = location
    if shadow_offset:
        shadow_left, shadow_top = shadow_offset
        draw.text((from_left + shadow_left, from_top + shadow_top), text, *args, fill=shadow_color, **kwargs)
    draw.text((from_left, from_top), text, *args, fill=color, **kwargs)


def raster_font_textwrap(text, wrap_width, font) -> list:
    if not text:
        return [""]
    if "\n" in text:
        lines = text.split("\n")
        return list(itertools.chain(*(raster_font_textwrap(line, wrap_width, font) for line in lines)))
    else:
        left, _, right, _ = font.getbbox(text)
        avg_width = right - left
        px_per_char = max(avg_width / len(text), 1)
        return textwrap.wrap(text, int(wrap_width / px_per_char))
