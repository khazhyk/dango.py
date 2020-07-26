import PIL

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
