import math
import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageDraw, ImageOps


class PhotoshopFX:
    """
    Photoshop-grade visual effects engine v3.0:
    - 12 Layer Blend Modes (Normal, Multiply, Screen, Overlay, Darken, Lighten,
      Add, Difference, Soft Light, Hard Light, Color Dodge, Luminosity)
    - Fade In / Fade Out opacity transitions
    - Adjustment Layers (Brightness, Contrast, Saturation, Gaussian Blur,
      Sharpen, Vignette, Color Temperature)
    - 12 Photographic Preset Filters
    - Drop Shadow layer styles
    - Alpha Mask support
    - Shape rendering (Rectangle, Ellipse, Triangle, Star, Line, Polygon)
    - Transition rendering (Fade, Wipe, Slide, Zoom, Dissolve, Flash, Glitch...)
    - NumPy-vectorized compositing path for performance
    """

    BLEND_MODES = [
        "Normal",
        "Multiplicar (Multiply)",
        "Trama / Aclarar (Screen)",
        "Superponer (Overlay)",
        "Oscurecer (Darken)",
        "Aclarar (Lighten)",
        "Añadir / Linear Dodge (Add)",
        "Diferencia (Difference)",
        "Luz Suave (Soft Light)",
        "Luz Fuerte (Hard Light)",
        "Sobreexponer (Color Dodge)",
        "Luminosidad (Luminosity)",
    ]

    FILTERS = [
        "Normal",
        "Blanco y Negro (Grayscale)",
        "Sepia Vintage",
        "Invertir Negativo",
        "Cálido (Golden Hour)",
        "Frío (Cinemático Teal)",
        "Alto Contraste Punch",
        "Desenfoque Suave",
        "Viñeta Cine",
        "HDR Tone Mapping",
        "Retro VHS",
        "Dreamy Glow",
    ]

    TRANSITION_TYPES = [
        "Fade", "Wipe Left", "Wipe Right", "Wipe Up", "Wipe Down",
        "Slide Left", "Slide Right", "Zoom In", "Zoom Out",
        "Dissolve", "Flash", "Spin", "Push", "Iris", "Glitch",
    ]

    # ------------------------------------------------------------------
    # Opacity / Fade helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Adjustment / Filter application
    # ------------------------------------------------------------------

    @staticmethod
    def apply_adjustments(img_rgba: Image.Image, filter_type: str = "Normal",
                          brightness: float = 1.0, contrast: float = 1.0,
                          saturation: float = 1.0, blur_radius: float = 0.0,
                          sharpen: float = 0.0, hue_shift: float = 0.0,
                          exposure: float = 0.0, vignette_strength: float = 0.0,
                          color_temp: float = 0.0) -> Image.Image:
        """Applies Photoshop-style adjustments: Filters, Brightness, Contrast,
        Saturation, Blur, Sharpen, Hue Shift, Exposure, Vignette, Color Temp."""
        if img_rgba is None:
            return img_rgba

        result = img_rgba.copy()
        has_alpha = result.mode == "RGBA"

        # 1. Preset Filters
        if filter_type == "Blanco y Negro (Grayscale)":
            alpha = result.split()[3] if has_alpha else None
            gray = ImageOps.grayscale(result.convert("RGB")).convert("RGBA" if has_alpha else "RGB")
            if has_alpha and alpha:
                gray.putalpha(alpha)
            result = gray

        elif filter_type == "Sepia Vintage":
            alpha = result.split()[3] if has_alpha else None
            gray = ImageOps.grayscale(result.convert("RGB"))
            sepia = ImageOps.colorize(gray, "#2e1a09", "#f5deb3").convert("RGBA" if has_alpha else "RGB")
            if has_alpha and alpha:
                sepia.putalpha(alpha)
            result = sepia

        elif filter_type == "Invertir Negativo":
            alpha = result.split()[3] if has_alpha else None
            inverted = ImageOps.invert(result.convert("RGB")).convert("RGBA" if has_alpha else "RGB")
            if has_alpha and alpha:
                inverted.putalpha(alpha)
            result = inverted

        elif filter_type == "Cálido (Golden Hour)":
            alpha = result.split()[3] if has_alpha else None
            r, g, b = result.convert("RGB").split()
            r = ImageEnhance.Brightness(r).enhance(1.15)
            b = ImageEnhance.Brightness(b).enhance(0.88)
            warm = Image.merge("RGB", (r, g, b)).convert("RGBA" if has_alpha else "RGB")
            if has_alpha and alpha:
                warm.putalpha(alpha)
            result = warm

        elif filter_type == "Frío (Cinemático Teal)":
            alpha = result.split()[3] if has_alpha else None
            r, g, b = result.convert("RGB").split()
            r = ImageEnhance.Brightness(r).enhance(0.88)
            b = ImageEnhance.Brightness(b).enhance(1.20)
            cool = Image.merge("RGB", (r, g, b)).convert("RGBA" if has_alpha else "RGB")
            if has_alpha and alpha:
                cool.putalpha(alpha)
            result = cool

        elif filter_type == "Alto Contraste Punch":
            result = ImageEnhance.Contrast(result).enhance(1.4)
            result = ImageEnhance.Color(result).enhance(1.25)

        elif filter_type == "Desenfoque Suave":
            result = result.filter(ImageFilter.GaussianBlur(2.0))

        elif filter_type == "Viñeta Cine":
            # Apply vignette + slight desaturate
            result = ImageEnhance.Color(result).enhance(0.85)
            vignette_strength = max(vignette_strength, 0.6)

        elif filter_type == "HDR Tone Mapping":
            alpha = result.split()[3] if has_alpha else None
            rgb = result.convert("RGB")
            rgb = ImageEnhance.Contrast(rgb).enhance(1.3)
            rgb = ImageEnhance.Color(rgb).enhance(1.2)
            r, g, b = rgb.split()
            r = ImageEnhance.Brightness(r).enhance(1.05)
            b = ImageEnhance.Brightness(b).enhance(0.95)
            hdr = Image.merge("RGB", (r, g, b)).convert("RGBA" if has_alpha else "RGB")
            if has_alpha and alpha:
                hdr.putalpha(alpha)
            result = hdr

        elif filter_type == "Retro VHS":
            alpha = result.split()[3] if has_alpha else None
            rgb = result.convert("RGB")
            # Slight color shift + noise-like saturation push
            r, g, b = rgb.split()
            r = ImageEnhance.Brightness(r).enhance(1.08)
            b = ImageEnhance.Brightness(b).enhance(0.9)
            vhs = Image.merge("RGB", (r, g, b))
            vhs = ImageEnhance.Color(vhs).enhance(1.4)
            vhs = vhs.filter(ImageFilter.GaussianBlur(0.4))
            vhs = vhs.convert("RGBA" if has_alpha else "RGB")
            if has_alpha and alpha:
                vhs.putalpha(alpha)
            result = vhs

        elif filter_type == "Dreamy Glow":
            alpha = result.split()[3] if has_alpha else None
            rgb = result.convert("RGB")
            glow = rgb.filter(ImageFilter.GaussianBlur(6))
            glow_arr = np.array(rgb, dtype=np.float32) * 0.7 + np.array(glow, dtype=np.float32) * 0.3
            glow_img = Image.fromarray(np.clip(glow_arr, 0, 255).astype(np.uint8))
            glow_img = ImageEnhance.Color(glow_img).enhance(1.2)
            glow_img = glow_img.convert("RGBA" if has_alpha else "RGB")
            if has_alpha and alpha:
                glow_img.putalpha(alpha)
            result = glow_img

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

        # 6. Sharpen
        if sharpen > 0.01:
            result = ImageEnhance.Sharpness(result).enhance(1.0 + min(10.0, sharpen))

        # 7. Exposure (simulated via brightness curve)
        if abs(exposure) > 0.01:
            factor = math.pow(2.0, exposure)
            result = ImageEnhance.Brightness(result).enhance(max(0.05, factor))

        # 8. Color Temperature
        if abs(color_temp) > 0.01:
            alpha = result.split()[3] if (result.mode == "RGBA") else None
            r, g, b = result.convert("RGB").split()
            if color_temp > 0:  # warm
                r = ImageEnhance.Brightness(r).enhance(1.0 + color_temp * 0.15)
                b = ImageEnhance.Brightness(b).enhance(1.0 - color_temp * 0.1)
            else:  # cool
                b = ImageEnhance.Brightness(b).enhance(1.0 + abs(color_temp) * 0.15)
                r = ImageEnhance.Brightness(r).enhance(1.0 - abs(color_temp) * 0.1)
            tmp = Image.merge("RGB", (r, g, b)).convert("RGBA" if alpha else "RGB")
            if alpha:
                tmp.putalpha(alpha)
            result = tmp

        # 9. Vignette
        if vignette_strength > 0.01:
            result = PhotoshopFX._apply_vignette(result, vignette_strength)

        return result

    @staticmethod
    def _apply_vignette(img: Image.Image, strength: float = 0.6) -> Image.Image:
        """Applies a radial vignette (dark corners) with given strength 0.0-1.0."""
        w, h = img.size
        has_alpha = img.mode == "RGBA"
        alpha_chan = img.split()[3] if has_alpha else None

        # Create radial gradient vignette mask
        vignette = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(vignette)
        cx, cy = w / 2.0, h / 2.0
        max_r = math.sqrt(cx ** 2 + cy ** 2)

        for y in range(h):
            for x in range(w):
                dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
                norm = min(1.0, dist / max_r)
                val = int(255 * (1.0 - norm * strength))
                vignette.putpixel((x, y), val)

        # Use faster numpy approach for large images
        cx_np, cy_np = w / 2.0, h / 2.0
        ys, xs = np.mgrid[0:h, 0:w]
        dist = np.sqrt((xs - cx_np) ** 2 + (ys - cy_np) ** 2)
        norm = np.clip(dist / max(1, max_r), 0, 1)
        vig_arr = np.clip(255 * (1.0 - norm * strength), 0, 255).astype(np.uint8)
        vignette = Image.fromarray(vig_arr, mode="L")

        rgb = img.convert("RGB")
        rgb_arr = np.array(rgb, dtype=np.float32)
        vig_float = np.array(vignette, dtype=np.float32) / 255.0
        result_arr = np.clip(rgb_arr * vig_float[:, :, np.newaxis], 0, 255).astype(np.uint8)
        result = Image.fromarray(result_arr).convert("RGBA" if has_alpha else "RGB")
        if has_alpha and alpha_chan is not None:
            result.putalpha(alpha_chan)
        return result

    # ------------------------------------------------------------------
    # Blend Mode Compositing
    # ------------------------------------------------------------------

    @staticmethod
    def apply_blend_composite(bg_pil: Image.Image, fg_pil: Image.Image,
                              pos: tuple, blend_mode: str = "Normal",
                              opacity: float = 1.0) -> Image.Image:
        """
        Blends fg_pil onto bg_pil at pos (x, y) according to Photoshop layer blend modes and opacity.
        Both images should be in RGBA. Uses NumPy for non-Normal modes for performance.
        """
        if opacity <= 0.001 or fg_pil is None:
            return bg_pil

        x, y = int(pos[0]), int(pos[1])
        bw, bh = bg_pil.size
        fw, fh = fg_pil.size

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(bw, x + fw)
        y2 = min(bh, y + fh)

        if x1 >= x2 or y1 >= y2:
            return bg_pil

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
            fg_crop = Image.merge("RGBA", (r, g, b, a))

        # Normal blend — fast PIL path
        if "Normal" in blend_mode or blend_mode == "Normal":
            bg_pil.paste(fg_crop, (x1, y1), fg_crop)
            return bg_pil

        # Advanced blend modes via NumPy
        bg_arr = np.array(bg_crop.convert("RGBA"), dtype=np.float32) / 255.0
        fg_arr = np.array(fg_crop.convert("RGBA"), dtype=np.float32) / 255.0

        bg_rgb = bg_arr[:, :, :3]
        fg_rgb = fg_arr[:, :, :3]
        fg_a = fg_arr[:, :, 3:4]

        blended_rgb = bg_rgb.copy()

        if "Multiplicar" in blend_mode or "Multiply" in blend_mode:
            blended_rgb = bg_rgb * fg_rgb

        elif "Trama" in blend_mode or "Screen" in blend_mode:
            blended_rgb = 1.0 - (1.0 - bg_rgb) * (1.0 - fg_rgb)

        elif "Superponer" in blend_mode or "Overlay" in blend_mode:
            mask = bg_rgb < 0.5
            blended_rgb = np.where(mask, 2.0 * bg_rgb * fg_rgb,
                                   1.0 - 2.0 * (1.0 - bg_rgb) * (1.0 - fg_rgb))

        elif "Oscurecer" in blend_mode or "Darken" in blend_mode:
            blended_rgb = np.minimum(bg_rgb, fg_rgb)

        elif "Aclarar" in blend_mode or "Lighten" in blend_mode:
            blended_rgb = np.maximum(bg_rgb, fg_rgb)

        elif "Añadir" in blend_mode or "Add" in blend_mode or "Linear Dodge" in blend_mode:
            blended_rgb = np.clip(bg_rgb + fg_rgb, 0, 1)

        elif "Diferencia" in blend_mode or "Difference" in blend_mode:
            blended_rgb = np.abs(bg_rgb - fg_rgb)

        elif "Luz Suave" in blend_mode or "Soft Light" in blend_mode:
            mask = fg_rgb < 0.5
            blended_rgb = np.where(
                mask,
                bg_rgb - (1.0 - 2.0 * fg_rgb) * bg_rgb * (1.0 - bg_rgb),
                bg_rgb + (2.0 * fg_rgb - 1.0) * (np.where(bg_rgb < 0.25,
                                                             ((16.0 * bg_rgb - 12.0) * bg_rgb + 4.0) * bg_rgb,
                                                             np.sqrt(np.clip(bg_rgb, 1e-6, 1.0))) - bg_rgb)
            )

        elif "Luz Fuerte" in blend_mode or "Hard Light" in blend_mode:
            mask = fg_rgb < 0.5
            blended_rgb = np.where(mask, 2.0 * bg_rgb * fg_rgb,
                                   1.0 - 2.0 * (1.0 - bg_rgb) * (1.0 - fg_rgb))

        elif "Sobreexponer" in blend_mode or "Color Dodge" in blend_mode:
            denom = np.clip(1.0 - fg_rgb, 1e-6, 1.0)
            blended_rgb = np.clip(bg_rgb / denom, 0, 1)

        elif "Luminosidad" in blend_mode or "Luminosity" in blend_mode:
            # Luminosity: take luminance from fg, keep hue+sat from bg
            bg_l = 0.2126 * bg_rgb[:, :, 0] + 0.7152 * bg_rgb[:, :, 1] + 0.0722 * bg_rgb[:, :, 2]
            fg_l = 0.2126 * fg_rgb[:, :, 0] + 0.7152 * fg_rgb[:, :, 1] + 0.0722 * fg_rgb[:, :, 2]
            diff_l = (fg_l - bg_l)[:, :, np.newaxis]
            blended_rgb = np.clip(bg_rgb + diff_l, 0, 1)

        # Alpha compositing: blend with original bg using fg alpha
        blended_rgb = np.clip(blended_rgb, 0, 1)
        out_rgb = bg_rgb * (1.0 - fg_a) + blended_rgb * fg_a
        out_arr = np.clip(np.concatenate([out_rgb, np.ones((*out_rgb.shape[:2], 1), dtype=np.float32)], axis=2) * 255, 0, 255).astype(np.uint8)

        composited = Image.fromarray(out_arr, "RGBA")
        bg_pil.paste(composited, (x1, y1), composited)
        return bg_pil

    # ------------------------------------------------------------------
    # Alpha Mask
    # ------------------------------------------------------------------

    @staticmethod
    def apply_mask(img_rgba: Image.Image, mask_path: str, invert: bool = False) -> Image.Image:
        """
        Applies a PNG mask image as the alpha channel of img_rgba.
        The mask is grayscale: white = fully visible, black = transparent.
        """
        if not mask_path or img_rgba is None:
            return img_rgba
        try:
            import os
            if not os.path.exists(mask_path):
                return img_rgba
            mask_img = Image.open(mask_path).convert("L")
            mask_img = mask_img.resize(img_rgba.size, Image.Resampling.LANCZOS)
            if invert:
                mask_img = ImageOps.invert(mask_img)
            # Combine with existing alpha
            existing_alpha = img_rgba.split()[3]
            combined = ImageChops.multiply(existing_alpha, mask_img)
            result = img_rgba.copy()
            result.putalpha(combined)
            return result
        except Exception:
            return img_rgba

    # ------------------------------------------------------------------
    # Shape Rendering
    # ------------------------------------------------------------------

    @staticmethod
    def render_shape(width: int, height: int, shape_type: str,
                     fill_color: str = "#CBA6F7", stroke_color: str = "#FFFFFF",
                     stroke_width: int = 2, corner_radius: int = 0,
                     star_points: int = 5) -> Image.Image:
        """
        Renders a vector shape onto a transparent RGBA canvas of given size.
        Supports: Rectangle, Ellipse, Triangle, Star, Line, Rounded Rectangle, Arrow, Hexagon.
        """
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx, cy = width / 2.0, height / 2.0
        margin = max(stroke_width, 2)
        box = [margin, margin, width - margin, height - margin]

        def _parse_color(c):
            try:
                r = int(c[1:3], 16)
                g = int(c[3:5], 16)
                b = int(c[5:7], 16)
                return (r, g, b, 255)
            except Exception:
                return (255, 255, 255, 255)

        fc = _parse_color(fill_color)
        sc = _parse_color(stroke_color)

        if shape_type == "Rectangle":
            draw.rectangle(box, fill=fc, outline=sc if stroke_width > 0 else None, width=stroke_width)

        elif shape_type == "Rounded Rectangle":
            r = max(0, corner_radius)
            draw.rounded_rectangle(box, radius=r, fill=fc,
                                   outline=sc if stroke_width > 0 else None, width=stroke_width)

        elif shape_type == "Ellipse":
            draw.ellipse(box, fill=fc, outline=sc if stroke_width > 0 else None, width=stroke_width)

        elif shape_type == "Triangle":
            pts = [
                (cx, margin),
                (width - margin, height - margin),
                (margin, height - margin),
            ]
            draw.polygon(pts, fill=fc, outline=sc if stroke_width > 0 else None)

        elif shape_type == "Star":
            n = max(3, star_points)
            outer_r = min(cx, cy) - margin
            inner_r = outer_r * 0.4
            pts = []
            for i in range(n * 2):
                angle = math.pi / n * i - math.pi / 2
                r_val = outer_r if (i % 2 == 0) else inner_r
                pts.append((cx + r_val * math.cos(angle), cy + r_val * math.sin(angle)))
            draw.polygon(pts, fill=fc, outline=sc if stroke_width > 0 else None)

        elif shape_type == "Hexagon":
            r_val = min(cx, cy) - margin
            pts = [(cx + r_val * math.cos(math.pi / 3 * i - math.pi / 6),
                    cy + r_val * math.sin(math.pi / 3 * i - math.pi / 6)) for i in range(6)]
            draw.polygon(pts, fill=fc, outline=sc if stroke_width > 0 else None)

        elif shape_type == "Line":
            draw.line([(margin, cy), (width - margin, cy)], fill=sc, width=max(2, stroke_width))

        elif shape_type == "Arrow":
            hw = (height - 2 * margin) * 0.4
            body_end_x = width - margin - hw * 1.5
            draw.rectangle([margin, cy - hw * 0.4, body_end_x, cy + hw * 0.4], fill=fc)
            pts = [(body_end_x, margin), (width - margin, cy), (body_end_x, height - margin)]
            draw.polygon(pts, fill=fc, outline=sc if stroke_width > 0 else None)

        return img

    # ------------------------------------------------------------------
    # Transition rendering
    # ------------------------------------------------------------------

    @staticmethod
    def apply_transition(frame_a: np.ndarray, frame_b: np.ndarray,
                         transition_type: str, progress: float) -> np.ndarray:
        """
        Blends frame_a (exiting) and frame_b (entering) based on transition_type and progress (0-1).
        Both frames must be BGR numpy arrays of the same size.
        Returns the composited BGR frame.
        """
        p = max(0.0, min(1.0, progress))
        h, w = frame_a.shape[:2]

        try:
            if transition_type == "Fade":
                return (frame_a * (1.0 - p) + frame_b * p).astype(np.uint8)

            elif transition_type == "Dissolve":
                # Additive dissolve
                add = np.clip(frame_a * (1.0 - p) + frame_b * p * 1.5, 0, 255)
                return (add * (1.0 - p * 0.5) + frame_b * p * 0.5).astype(np.uint8)

            elif transition_type == "Flash":
                white = np.full_like(frame_a, 255)
                if p < 0.5:
                    t = p * 2.0
                    return (frame_a * (1.0 - t) + white * t).astype(np.uint8)
                else:
                    t = (p - 0.5) * 2.0
                    return (white * (1.0 - t) + frame_b * t).astype(np.uint8)

            elif transition_type in ("Wipe Left", "Wipe Right", "Wipe Up", "Wipe Down"):
                result = frame_a.copy()
                if transition_type == "Wipe Left":
                    cut = max(0, min(w, int(w * p)))
                    result[:, :cut] = frame_b[:, :cut]
                elif transition_type == "Wipe Right":
                    cut = max(0, min(w, int(w * (1.0 - p))))
                    result[:, cut:] = frame_b[:, cut:]
                elif transition_type == "Wipe Up":
                    cut = max(0, min(h, int(h * p)))
                    result[:cut, :] = frame_b[:cut, :]
                elif transition_type == "Wipe Down":
                    cut = max(0, min(h, int(h * (1.0 - p))))
                    result[cut:, :] = frame_b[cut:, :]
                return result

            elif transition_type in ("Slide Left", "Slide Right", "Push"):
                result = frame_b.copy()
                offset = int(w * (1.0 - p))
                if transition_type in ("Slide Left", "Push"):
                    if offset > 0:
                        result[:, offset:] = frame_a[:, :w - offset]
                        result[:, :offset] = frame_b[:, :offset]
                else:
                    if offset > 0:
                        result[:, :w - offset] = frame_a[:, offset:]
                        result[:, w - offset:] = frame_b[:, w - offset:]
                return result

            elif transition_type == "Zoom In":
                import cv2
                scale = 1.0 + (1.0 - p) * 0.5
                M = cv2.getRotationMatrix2D((w / 2, h / 2), 0, scale)
                zoomed_b = cv2.warpAffine(frame_b, M, (w, h))
                return (frame_a * (1.0 - p) + zoomed_b * p).astype(np.uint8)

            elif transition_type == "Zoom Out":
                import cv2
                scale = 1.0 + p * 0.5
                M = cv2.getRotationMatrix2D((w / 2, h / 2), 0, scale)
                zoomed_a = cv2.warpAffine(frame_a, M, (w, h))
                return (zoomed_a * (1.0 - p) + frame_b * p).astype(np.uint8)

            elif transition_type == "Spin":
                import cv2
                angle = p * 360.0
                M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0 - p * 0.3)
                spun = cv2.warpAffine(frame_a, M, (w, h))
                return (spun * (1.0 - p) + frame_b * p).astype(np.uint8)

            elif transition_type == "Iris":
                result = frame_a.copy()
                cx_i, cy_i = w // 2, h // 2
                max_r = math.sqrt(cx_i ** 2 + cy_i ** 2)
                radius = int(max_r * p)
                ys, xs = np.mgrid[0:h, 0:w]
                mask = ((xs - cx_i) ** 2 + (ys - cy_i) ** 2) <= radius ** 2
                result[mask] = frame_b[mask]
                return result

            elif transition_type == "Glitch":
                result = (frame_a * (1.0 - p) + frame_b * p).astype(np.uint8)
                if 0.2 < p < 0.8:
                    import random
                    for _ in range(int(5 * (1 - abs(p - 0.5) * 2))):
                        gy = random.randint(0, h - 1)
                        goff = random.randint(-20, 20)
                        gline = result[gy].copy()
                        shifted = np.roll(gline, goff, axis=0)
                        result[gy] = shifted
                return result

        except Exception:
            pass

        # Fallback: crossfade
        return (frame_a * (1.0 - p) + frame_b * p).astype(np.uint8)

    # ------------------------------------------------------------------
    # Adjustment Layer Application
    # ------------------------------------------------------------------

    @staticmethod
    def apply_adjustment_layer(frame_bgr: np.ndarray, adj_layer) -> np.ndarray:
        """
        Applies an AdjustmentLayer's parameters to a full BGR numpy frame.
        Returns modified BGR frame.
        """
        import cv2
        try:
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb).convert("RGBA")

            pil_result = PhotoshopFX.apply_adjustments(
                pil_img,
                filter_type=getattr(adj_layer, 'filter_type', 'Normal'),
                brightness=getattr(adj_layer, 'brightness', 1.0),
                contrast=getattr(adj_layer, 'contrast', 1.0),
                saturation=getattr(adj_layer, 'saturation', 1.0),
                blur_radius=getattr(adj_layer, 'blur_radius', 0.0),
                sharpen=getattr(adj_layer, 'sharpen', 0.0),
                hue_shift=getattr(adj_layer, 'hue_shift', 0.0),
                exposure=getattr(adj_layer, 'exposure', 0.0),
                vignette_strength=getattr(adj_layer, 'vignette_strength', 0.0),
                color_temp=getattr(adj_layer, 'color_temp', 0.0),
            )

            # Apply vignette if requested
            vig = getattr(adj_layer, 'vignette_strength', 0.0)
            if vig > 0.01:
                pil_result = PhotoshopFX._apply_vignette(pil_result, vig)

            out_rgb = np.array(pil_result.convert("RGB"))
            result_bgr = cv2.cvtColor(out_rgb, cv2.COLOR_RGB2BGR)

            # Blend with original based on opacity
            op = max(0.0, min(1.0, getattr(adj_layer, 'opacity', 1.0)))
            if op < 0.999:
                result_bgr = (frame_bgr * (1.0 - op) + result_bgr * op).astype(np.uint8)

            return result_bgr
        except Exception:
            return frame_bgr

    # ------------------------------------------------------------------
    # Border and Corners (unchanged from v2)
    # ------------------------------------------------------------------

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

        if radius > 0:
            mask = Image.new("L", (w, h), 0)
            draw_m = ImageDraw.Draw(mask)
            draw_m.rounded_rectangle((0, 0, w, h), radius=min(radius, min(w, h) // 2), fill=255)
            cur_alpha = result.split()[3]
            combined_alpha = ImageChops.multiply(cur_alpha, mask)
            result.putalpha(combined_alpha)

        if border_width > 0:
            draw_b = ImageDraw.Draw(result)
            half_bw = border_width / 2.0
            rect_coords = (half_bw, half_bw, w - half_bw, h - half_bw)
            if radius > 0:
                draw_b.rounded_rectangle(rect_coords, radius=max(1, radius - int(half_bw)),
                                         outline=border_color, width=border_width)
            else:
                draw_b.rectangle(rect_coords, outline=border_color, width=border_width)

        return result

    # ------------------------------------------------------------------
    # Rotation (unchanged from v2)
    # ------------------------------------------------------------------

    @staticmethod
    def apply_rotation(img_rgba: Image.Image, angle_deg: float = 0.0) -> Image.Image:
        """Rotates img_rgba by angle_deg (0-360) preserving alpha transparency."""
        if img_rgba is None or abs(angle_deg % 360) < 0.1:
            return img_rgba
        return img_rgba.rotate(-angle_deg, resample=Image.Resampling.BICUBIC, expand=True)

    # ------------------------------------------------------------------
    # NumPy fast alpha blend (GPU-style compositing path)
    # ------------------------------------------------------------------

    @staticmethod
    def alpha_blend_numpy(bg: np.ndarray, fg: np.ndarray, x: int, y: int,
                          opacity: float = 1.0) -> np.ndarray:
        """
        High-performance NumPy Porter-Duff 'over' compositing.
        bg and fg must be RGBA uint8 numpy arrays.
        Returns the modified bg (in-place safe).
        """
        h_bg, w_bg = bg.shape[:2]
        h_fg, w_fg = fg.shape[:2]

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w_bg, x + w_fg)
        y2 = min(h_bg, y + h_fg)

        if x1 >= x2 or y1 >= y2:
            return bg

        fx1 = x1 - x
        fy1 = y1 - y
        fx2 = fx1 + (x2 - x1)
        fy2 = fy1 + (y2 - y1)

        fg_crop = fg[fy1:fy2, fx1:fx2].astype(np.float32)
        bg_crop = bg[y1:y2, x1:x2].astype(np.float32)

        fg_alpha = (fg_crop[:, :, 3:4] / 255.0) * opacity
        bg_alpha = bg_crop[:, :, 3:4] / 255.0

        out_alpha = fg_alpha + bg_alpha * (1.0 - fg_alpha)
        denom = np.where(out_alpha > 0, out_alpha, 1.0)
        out_rgb = (fg_crop[:, :, :3] * fg_alpha + bg_crop[:, :, :3] * bg_alpha * (1.0 - fg_alpha)) / denom

        result = np.concatenate([np.clip(out_rgb, 0, 255), np.clip(out_alpha * 255, 0, 255)], axis=2).astype(np.uint8)
        bg[y1:y2, x1:x2] = result
        return bg
