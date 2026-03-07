# scripts/vectorize.py
import vtracer

# This mathematically recreates the raster image as infinitely scalable SVG code
vtracer.convert_image_to_svg_py(
    "/Users/siddhu/qwen-studio/branding/favicon.png",
    "/Users/siddhu/qwen-studio/branding/favicon.svg",
    colormode="color",        # Keep original colors
    hierarchical="stacked",   # Better for complex logos
    mode="spline",            # Smooth curves instead of jagged polygons
    filter_speckle=4,         # Remove low-res noise/artifacts
    color_precision=6,        # High color accuracy
    corner_threshold=60,
    length_threshold=4.0
)