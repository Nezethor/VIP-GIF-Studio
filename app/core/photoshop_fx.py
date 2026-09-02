import math
import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageDraw, ImageOps

class PhotoshopFX:
    """
    Photoshop-grade visual effects engine:
    - Layer Blend Modes (Normal, Multiply, Screen, Overlay, Darken, Lighten, Add, Difference, Soft Light)
    - Fade In / Fade Out opacity transitions
    - Adjustment Layers (Brightness, Contrast, Saturation, Gaussian Blur)
    - Photographic LUT/Filter Presets (B&W, Sepia Vintage, Invert, Cinematic Cool, Golden Warm, Punch)
    - Drop Shadow layer styles
    """

    BLEND_MODES = [
        "Normal",
        "Multiplicar (Multiply)",
        "Trama / Aclarar (Screen)",
        "Superponer (Overlay)",
        "Oscurecer (Darken)",
        "Aclarar (Lighten)",
        "Añadir / Linear Dodge (Add)",
        "Diferencia (Difference)"
    ]

    FILTERS = [
        "Normal",
        "Blanco y Negro (Grayscale)",
        "Sepia Vintage",
        "Invertir Negativo",
        "Cálido (Golden Hour)",
        "Frío (Cinemático Teal)",
        "Alto Contraste Punch",
        "Desenfoque Suave"
    ]

    @staticmethod
    def compute_opacity_with_fade(current_sec: float, start_sec: float, end_sec: float,
                                  base_opacity: float = 1.0, fade_in_sec: float = 0.0,
                                  fade_out_sec: float = 0.0) -> float:
        """Calculates effective opacity accounting for base opacity and smooth Fade In / Fade Out transitions."""
        if current_sec < start_sec or current_sec > end_sec:
            return 0.0

        op = max(0.0, min(1.0, base_opacity))
        rel_in = current_sec - start_sec
        rel_out = end_sec - current_sec

        if fade_in_sec > 0.001 and rel_in < fade_in_sec:
            in_factor = max(0.0, min(1.0, rel_in / fade_in_sec))
            op *= in_factor

        if fade_out_sec > 0.001 and rel_out < fade_out_sec:
            out_factor = max(0.0, min(1.0, rel_out / fade_out_sec))
            op *= out_factor

        return max(0.0, min(1.0, op))

    @staticmethod
    def apply_adjustments(img_rgba: Image.Image, filter_type: str = "Normal",
                          brightness: float = 1.0, contrast: float = 1.0,
                          saturation: float = 1.0, blur_radius: float = 0.0) -> Image.Image:
        """Applies Photoshop-style adjustments: Brightness, Contrast, Saturation, Blur and Preset Filters."""
        if img_rgba is None:
            return img_rgba

        result = img_rgba.copy()

        # 1. Preset Filter
        if filter_type == "Blanco y Negro (Grayscale)":
            alpha = result.split()[3]
            gray = ImageOps.grayscale(result.convert("RGB")).convert("RGBA")
            gray.putalpha(alpha)
            result = gray
        elif filter_type == "Sepia Vintage":
            alpha = result.split()[3]
            gray = ImageOps.grayscale(result.convert("RGB"))
            sepia = ImageOps.colorize(gray, "#2e1a09", "#f5deb3").convert("RGBA")
            sepia.putalpha(alpha)
            result = sepia
        elif filter_type == "Invertir Negativo":
            alpha = result.split()[3]
            inverted = ImageOps.invert(result.convert("RGB")).convert("RGBA")
            inverted.putalpha(alpha)
            result = inverted
        elif filter_type == "Cálido (Golden Hour)":
            alpha = result.split()[3]
            r, g, b = result.convert("RGB").split()
            r = ImageEnhance.Brightness(r).enhance(1.15)
            b = ImageEnhance.Brightness(b).enhance(0.88)
            warm = Image.merge("RGB", (r, g, b)).convert("RGBA")
            warm.putalpha(alpha)
            result = warm
        elif filter_type == "Frío (Cinemático Teal)":
            alpha = result.split()[3]
            r, g, b = result.convert("RGB").split()
            r = ImageEnhance.Brightness(r).enhance(0.88)
            b = ImageEnhance.Brightness(b).enhance(1.20)
            cool = Image.merge("RGB", (r, g, b)).convert("RGBA")
            cool.putalpha(alpha)
            result = cool
        elif filter_type == "Alto Contraste Punch":
            result = ImageEnhance.Contrast(result).enhance(1.4)
            result = ImageEnhance.Color(result).enhance(1.25)
        elif filter_type == "Desenfoque Suave":
            result = result.filter(ImageFilter.GaussianBlur(2.0))

        # 2. Brightness
        if abs(brightness - 1.0) > 0.01:
            result = ImageEnhance.Brightness(result).enhance(max(0.1, brightness))

        # 3. Contrast
        if abs(contrast - 1.0) > 0.01:
            result = ImageEnhance.Contrast(result).enhance(max(0.1, contrast))

        # 4. Saturation
        if abs(saturation - 1.0) > 0.01:
            result = ImageEnhance.Color(result).enhance(max(0.0, saturation))

        # 5. Gaussian Blur
        if blur_radius > 0.1:
            result = result.filter(ImageFilter.GaussianBlur(min(20.0, blur_radius)))

        return result

    @staticmethod
    def apply_blend_composite(bg_pil: Image.Image, fg_pil: Image.Image,
                              pos: tuple, blend_mode: str = "Normal",
                              opacity: float = 1.0) -> Image.Image:
        """
        Blends fg_pil onto bg_pil at pos (x, y) according to Photoshop layer blend modes and opacity.
        Both images should be in RGBA.
        """
        if opacity <= 0.001 or fg_pil is None:
            return bg_pil

        x, y = pos
        bw, bh = bg_pil.size
        fw, fh = fg_pil.size

        # Compute overlap bounds
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(bw, x + fw)
        y2 = min(bh, y + fh)

        if x1 >= x2 or y1 >= y2:
            return bg_pil

        # Crop corresponding region from fg
        fx1 = x1 - x
        fy1 = y1 - y
        fx2 = fx1 + (x2 - x1)
        fy2 = fy1 + (y2 - y1)

        fg_crop = fg_pil.crop((fx1, fy1, fx2, fy2))
        bg_crop = bg_pil.crop((x1, y1, x2, y2))

        # Scale alpha with opacity
        if opacity < 0.999:
            r, g, b, a = fg_crop.split()
            a = a.point(lambda p: int(p * opacity))
            fg_crop.putalpha(a)

        # Standard Normal Blend (Porter-Duff over)
        if "Normal" in blend_mode or blend_mode == "Normal":
            bg_pil.paste(fg_crop, (x1, y1), fg_crop)
            return bg_pil

        # Advanced Photoshop Blend Modes
        bg_rgb = bg_crop.convert("RGB")
        fg_rgb = fg_crop.convert("RGB")
        fg_alpha = fg_crop.split()[3]

        blended_rgb = bg_rgb

        if "Multiplicar" in blend_mode or "Multiply" in blend_mode:
            blended_rgb = ImageChops.multiply(bg_rgb, fg_rgb)
        elif "Trama" in blend_mode or "Screen" in blend_mode:
            blended_rgb = ImageChops.screen(bg_rgb, fg_rgb)
        elif "Superponer" in blend_mode or "Overlay" in blend_mode:
            blended_rgb = ImageChops.overlay(bg_rgb, fg_rgb)
        elif "Oscurecer" in blend_mode or "Darken" in blend_mode:
            blended_rgb = ImageChops.darker(bg_rgb, fg_rgb)
        elif "Aclarar" in blend_mode or "Lighten" in blend_mode:
            blended_rgb = ImageChops.lighter(bg_rgb, fg_rgb)
        elif "Añadir" in blend_mode or "Add" in blend_mode:
            blended_rgb = ImageChops.add(bg_rgb, fg_rgb)
        elif "Diferencia" in blend_mode or "Difference" in blend_mode:
            blended_rgb = ImageChops.difference(bg_rgb, fg_rgb)

        # Convert blended back to RGBA with original fg alpha
        blended_rgba = blended_rgb.convert("RGBA")
        blended_rgba.putalpha(fg_alpha)

        # Paste composite onto bg
        bg_pil.paste(blended_rgba, (x1, y1), blended_rgba)
        return bg_pil

    @staticmethod
    def apply_border_and_corners(img_rgba: Image.Image, radius: int = 0,
                                 border_width: int = 0, border_color: str = "#FFFFFF") -> Image.Image:
        """Applies rounded corners and optional stroke border around img_rgba."""
        if img_rgba is None:
            return img_rgba

        w, h = img_rgba.size
        if radius <= 0 and border_width <= 0:
            return img_rgba

        result = img_rgba.copy()

        # Rounded corners mask
        if radius > 0:
            mask = Image.new("L", (w, h), 0)
            draw_m = ImageDraw.Draw(mask)
            draw_m.rounded_rectangle((0, 0, w, h), radius=min(radius, min(w, h) // 2), fill=255)
            cur_alpha = result.split()[3]
            combined_alpha = ImageChops.multiply(cur_alpha, mask)
            result.putalpha(combined_alpha)

        # Border Stroke
        if border_width > 0:
            draw_b = ImageDraw.Draw(result)
            half_bw = border_width / 2.0
            rect_coords = (half_bw, half_bw, w - half_bw, h - half_bw)
            if radius > 0:
                draw_b.rounded_rectangle(rect_coords, radius=max(1, radius - int(half_bw)), outline=border_color, width=border_width)
            else:
                draw_b.rectangle(rect_coords, outline=border_color, width=border_width)

        return result

    @staticmethod
    def apply_rotation(img_rgba: Image.Image, angle_deg: float = 0.0) -> Image.Image:
        """Rotates img_rgba by angle_deg (0-360) preserving alpha transparency."""
        if img_rgba is None or abs(angle_deg % 360) < 0.1:
            return img_rgba
        return img_rgba.rotate(angle_deg, resample=Image.Resampling.BICUBIC, expand=True)

