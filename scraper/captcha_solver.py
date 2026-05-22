"""
TikTok CAPTCHA Solver - 100% Tự động, không cần người dùng can thiệp.

Thuật toán lấy từ các dự án mã nguồn mở:
- vsmutok/PuzzleCaptchaSolver (MIT License) - OpenCV edge detection + template matching
- xtekky/TikTok-Captcha-Solver - Sobel operator cho TikTok cụ thể

Hỗ trợ: Slide Puzzle, Rotate, Shape Match, Whirl/3D.
"""

import asyncio
import random
import math
import time
import base64
import io
import os
import re

import cv2
import numpy as np


def _log(msg):
    try:
        print(f"  [CAPTCHA] {msg}")
    except:
        try:
            print(f"  [CAPTCHA] {msg.encode('ascii', errors='ignore').decode('ascii')}")
        except:
            pass


# ═══════════════════════════════════════════════════════════════════
# PHẦN 1: XỬ LÝ ẢNH - Thuật toán từ GitHub
# ═══════════════════════════════════════════════════════════════════

class PuzzleSolver:
    """
    Giải slide puzzle bằng Sobel operator + template matching.
    Thuật toán gốc: xtekky/TikTok-Captcha-Solver (GitHub, 157 stars)
    """

    @staticmethod
    def find_offset(bg_bytes, piece_bytes):
        """
        Giải slide puzzle bằng các phương pháp tối ưu xếp chồng:
        1. Sobel Edge Template Matching (Chính xác nhất - thuật toán xtekky/TikTok-Captcha-Solver)
        2. Edge Alpha Bounding Box Matching (Dự phòng)
        3. GapDetector (Canny density fallback)
        """
        # Helper function để tính Sobel
        def get_sobel(img):
            img_blur = cv2.GaussianBlur(img, (3, 3), 0)
            gray = cv2.cvtColor(img_blur, cv2.COLOR_BGR2GRAY)
            grad_x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=3, scale=1, delta=0, borderType=cv2.BORDER_DEFAULT)
            grad_y = cv2.Sobel(gray, cv2.CV_16S, 0, 1, ksize=3, scale=1, delta=0, borderType=cv2.BORDER_DEFAULT)
            abs_grad_x = cv2.convertScaleAbs(grad_x)
            abs_grad_y = cv2.convertScaleAbs(grad_y)
            return cv2.addWeighted(abs_grad_x, 0.5, abs_grad_y, 0.5, 0)

        # 1. Thử dùng Masked Sobel Edge Template Matching (Tối ưu nhất, chống nhiễu nền)
        try:
            bg_img = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)
            piece_img = cv2.imdecode(np.frombuffer(piece_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
            
            if bg_img is not None and piece_img is not None:
                _log(f"bg_img shape: {bg_img.shape}, piece_img shape: {piece_img.shape}")
                
                # Lưu ảnh để gỡ lỗi trực quan
                try:
                    cv2.imwrite("debug_bg.png", bg_img)
                    cv2.imwrite("debug_piece.png", piece_img)
                except:
                    pass

                # Tiền xử lý Sobel cho ảnh background
                bg_sobel = get_sobel(bg_img)
                
                # Tiền xử lý Sobel cho ảnh piece (trộn với alpha để tránh nhiễu viền ngoài)
                if len(piece_img.shape) == 3 and piece_img.shape[2] == 4:
                    alpha = piece_img[:, :, 3] / 255.0
                    bgr = piece_img[:, :, :3]
                    piece_bgr = np.zeros_like(bgr)
                    for c in range(3):
                        piece_bgr[:, :, c] = (bgr[:, :, c] * alpha).astype(np.uint8)
                    piece_sobel = get_sobel(piece_bgr)
                    
                    # Tạo mặt nạ từ kênh Alpha (để chỉ khớp vùng thực của mảnh ghép, bỏ qua nền trong suốt)
                    mask = (piece_img[:, :, 3] > 0).astype(np.uint8) * 255
                else:
                    piece_sobel = get_sobel(piece_img)
                    mask = np.ones(piece_sobel.shape, dtype=np.uint8) * 255

                # Sử dụng TM_CCORR_NORMED kèm mask để khớp chính xác tuyệt đối
                matched = cv2.matchTemplate(bg_sobel, piece_sobel, cv2.TM_CCORR_NORMED, mask=mask)
                _, max_val, _, max_loc = cv2.minMaxLoc(matched)
                
                _log(f"Masked Sobel Matching: x={max_loc[0]}, confidence={max_val:.3f}")
                # Kênh so khớp có mask TM_CCORR_NORMED có confidence cao và chuẩn xác hơn
                if max_val > 0.50:
                    _log(f"✅ Chọn tọa độ từ Masked Sobel Matching: x={max_loc[0]}")
                    return max_loc[0]
        except Exception as sobel_err:
            _log(f"Lỗi Masked Sobel Matching: {sobel_err}")

        # 2. Dự phòng 1: Edge Alpha Bounding Box Matching
        try:
            bg_img = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)
            piece_img = cv2.imdecode(np.frombuffer(piece_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
            
            if bg_img is not None and piece_img is not None:
                if len(piece_img.shape) == 3 and piece_img.shape[2] == 4:
                    alpha = piece_img[:, :, 3]
                    for thresh_val in [100]:
                        pts = np.argwhere(alpha > thresh_val)
                        if len(pts) > 0:
                            y1, x1 = pts.min(axis=0)
                            y2, x2 = pts.max(axis=0)
                            cropped_alpha = alpha[y1:y2+1, x1:x2+1]
                            piece_edges = cv2.Canny(cropped_alpha, 100, 200)
                            bg_gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY)
                            bg_edges = cv2.Canny(bg_gray, 100, 200)
                            matched = cv2.matchTemplate(bg_edges, piece_edges, cv2.TM_CCOEFF_NORMED)
                            _, max_val, _, max_loc = cv2.minMaxLoc(matched)
                            actual_x = max_loc[0] - x1
                            if actual_x >= 0 and max_val > 0.12:
                                _log(f"✅ Chọn tọa độ từ Edge Alpha Matching (Dự phòng): x={actual_x}, confidence={max_val:.3f}")
                                return actual_x
        except Exception as mask_err:
            _log(f"Lỗi Edge Alpha Matching (Dự phòng): {mask_err}")

        # 3. Dự phòng 2: Gap Detector (Canny Density)
        try:
            gap_x = GapDetector.find_gap_x(bg_bytes)
            if gap_x is not None:
                _log(f"✅ Chọn tọa độ từ Gap Detector (Dự phòng): x={gap_x}")
                return gap_x
        except Exception as gap_err:
            _log(f"Lỗi Gap Detector: {gap_err}")

        return None

    @staticmethod
    def from_bytes(puzzle_bytes, piece_bytes):
        """Tạo solver từ raw bytes thay vì base64."""
        puzzle_b64 = base64.b64encode(puzzle_bytes)
        piece_b64 = base64.b64encode(piece_bytes)
        return PuzzleSolver(puzzle_b64, piece_b64)

    def __init__(self, base64_puzzle, base64_piece):
        self.puzzle = base64_puzzle
        self.piece = base64_piece

    def get_position(self):
        """Tìm vị trí x chính xác của mảnh ghép."""
        puzzle = self._preprocess(self.puzzle)
        piece = self._preprocess(self.piece)

        if puzzle is None or piece is None:
            return None

        # Đảm bảo piece nhỏ hơn puzzle
        if piece.shape[0] > puzzle.shape[0] or piece.shape[1] > puzzle.shape[1]:
            _log("Piece lớn hơn puzzle, đổi vai trò...")
            puzzle, piece = piece, puzzle

        matched = cv2.matchTemplate(puzzle, piece, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(matched)
        _log(f"Template matching: x={max_loc[0]}, confidence={max_val:.3f}")
        
        # Nếu độ tin cậy quá thấp, trả về None để dùng GapDetector (Canny Edge)
        if max_val < 0.55:
            _log("Độ tin cậy thấp, bỏ qua PuzzleSolver...")
            return None
            
        return max_loc[0]

    def _preprocess(self, img_b64):
        """Tiền xử lý: decode → grayscale → Sobel edge detection."""
        try:
            raw = np.frombuffer(base64.b64decode(img_b64), dtype="uint8")
            img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if img is None:
                return None
            return self._sobel_operator(img)
        except Exception as e:
            _log(f"Lỗi preprocessing: {e}")
            return None

    def _sobel_operator(self, img):
        """Sobel edge detection - hiệu quả hơn Canny cho TikTok puzzle."""
        img = cv2.GaussianBlur(img, (3, 3), 0)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        grad_x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=3,
                           scale=1, delta=0, borderType=cv2.BORDER_DEFAULT)
        grad_y = cv2.Sobel(gray, cv2.CV_16S, 0, 1, ksize=3,
                           scale=1, delta=0, borderType=cv2.BORDER_DEFAULT)
        abs_grad_x = cv2.convertScaleAbs(grad_x)
        abs_grad_y = cv2.convertScaleAbs(grad_y)
        grad = cv2.addWeighted(abs_grad_x, 0.5, abs_grad_y, 0.5, 0)
        return grad


class GapDetector:
    """
    Phát hiện khe hở (gap) trong ảnh nền khi KHÔNG có ảnh mảnh ghép.
    Thuật toán gốc: vsmutok/PuzzleCaptchaSolver (MIT License, 83 stars)
    """

    @staticmethod
    def find_gap_x(bg_bytes):
        """Tìm vị trí x của khe hở trong ảnh nền."""
        try:
            raw = np.frombuffer(bg_bytes, dtype="uint8")
            img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if img is None:
                return None

            # Bỏ cắt whitespace vì nó làm sai lệch tọa độ gốc của ảnh TikTok
            # img = GapDetector._remove_whitespace(img)

            # Edge detection
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 100, 200)

            # Tìm vùng edge dày đặc (chính là khe hở puzzle)
            h, w = edges.shape
            col_density = edges.sum(axis=0).astype(float)

            # Bỏ qua 10% mép trái phải (thường là viền ảnh)
            margin = int(w * 0.10)
            col_density[:margin] = 0
            col_density[-margin:] = 0

            # Tìm vùng mật độ cao nhất
            kernel_size = 40  # Kích thước mảnh ghép ước chừng ~40px
            if w < kernel_size * 2:
                kernel_size = max(10, w // 4)

            best_x = margin
            best_sum = 0
            for x in range(margin, w - kernel_size):
                region_sum = col_density[x:x + kernel_size].sum()
                if region_sum > best_sum:
                    best_sum = region_sum
                    best_x = x

            # best_x là cạnh trái của khe hở. Trả về best_x vì slider map với cạnh trái.
            _log(f"Gap detection: x={best_x} (center={best_x + kernel_size // 2})")
            return best_x

        except Exception as e:
            _log(f"Lỗi gap detection: {e}")
            return None

    @staticmethod
    def _remove_whitespace(img):
        """Cắt bỏ viền trắng/trong suốt xung quanh ảnh."""
        try:
            rows, cols = img.shape[:2]
            min_x, min_y, max_x, max_y = rows, cols, 0, 0
            for x in range(rows):
                for y in range(cols):
                    pixel = img[x, y]
                    if len(set(pixel)) >= 2:  # Không phải pixel đồng màu
                        min_x = min(x, min_x)
                        min_y = min(y, min_y)
                        max_x = max(x, max_x)
                        max_y = max(y, max_y)
            if max_x > min_x and max_y > min_y:
                return img[min_x:max_x, min_y:max_y]
        except:
            pass
        return img


class RotateSolver:
    """
    Giải xoay puzzle (Rotate CAPTCHA) bằng cách xoay góc và so khớp.
    """
    @staticmethod
    def find_rotation_angle(bg_bytes, piece_bytes):
        """
        Tìm góc xoay tối ưu để khớp mảnh xoay (piece) vào hình nền (bg).
        Góc trả về thuộc [0, 360].
        """
        try:
            # Decode images
            raw_bg = np.frombuffer(bg_bytes, dtype="uint8")
            bg = cv2.imdecode(raw_bg, cv2.IMREAD_GRAYSCALE)
            
            raw_pc = np.frombuffer(piece_bytes, dtype="uint8")
            pc = cv2.imdecode(raw_pc, cv2.IMREAD_GRAYSCALE)
            
            if bg is None or pc is None:
                return None
                
            # Đảm bảo kích thước khớp hoặc crop phần tâm của bg bằng kích thước pc
            h_pc, w_pc = pc.shape[:2]
            h_bg, w_bg = bg.shape[:2]
            
            cy, cx = h_bg // 2, w_bg // 2
            # Crop vùng tâm của background có cùng kích thước với piece
            bg_crop = bg[max(0, cy - h_pc//2) : min(h_bg, cy + h_pc//2), 
                         max(0, cx - w_pc//2) : min(w_bg, cx + w_pc//2)]
                         
            # Đảm bảo bg_crop và pc có cùng kích thước
            if bg_crop.shape != pc.shape:
                bg_crop = cv2.resize(bg_crop, (w_pc, h_pc))
                
            # Áp dụng Canny để làm nổi bật các cạnh (giảm ảnh hưởng của màu sắc/độ sáng)
            bg_edges = cv2.Canny(bg_crop, 50, 150)
            pc_edges = cv2.Canny(pc, 50, 150)
            
            best_angle = 0
            max_val = -1
            
            # Thử xoay mảnh ghép từ 0 đến 360 độ, mỗi bước 2 độ
            center = (w_pc // 2, h_pc // 2)
            for angle in range(0, 360, 2):
                # Xoay mảnh ghép theo chiều kim đồng hồ (OpenCV dùng góc âm để xoay CW)
                rot_mat = cv2.getRotationMatrix2D(center, -angle, 1.0)
                rotated = cv2.warpAffine(pc_edges, rot_mat, (w_pc, h_pc), flags=cv2.INTER_LINEAR)
                
                # So sánh độ tương đồng bằng template matching
                res = cv2.matchTemplate(bg_edges, rotated, cv2.TM_CCOEFF_NORMED)
                _, val, _, _ = cv2.minMaxLoc(res)
                
                if val > max_val:
                    max_val = val
                    best_angle = angle
                    
            _log(f"Rotate solver: tìm thấy góc xoay tối ưu = {best_angle}° với độ tin cậy {max_val:.3f}")
            return best_angle
        except Exception as e:
            _log(f"Lỗi RotateSolver: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════
# PHẦN 2: CHUYỂN ĐỘNG CHUỘT GIỐNG NGƯỜI THẬT
# ═══════════════════════════════════════════════════════════════════

def _bezier_curve(start, end, num_points=45):
    """Tạo quỹ đạo Bezier curve tự nhiên với 2 control points ngẫu nhiên."""
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy

    # Tính toán control points tỷ lệ theo dx, dy (hỗ trợ cả đường chéo)
    # Giữ variance nhỏ để tránh ra khỏi nút kéo
    cp1 = (
        sx + dx * random.uniform(0.2, 0.4) + random.randint(-3, 3),
        sy + dy * random.uniform(0.2, 0.4) + random.randint(-4, 4)
    )
    cp2 = (
        sx + dx * random.uniform(0.6, 0.8) + random.randint(-3, 3),
        sy + dy * random.uniform(0.6, 0.8) + random.randint(-4, 4)
    )

    points = []
    for i in range(num_points + 1):
        t = i / num_points
        # Ease-out
        t = t * (2 - t)

        x = ((1 - t) ** 3 * sx + 3 * (1 - t) ** 2 * t * cp1[0] +
             3 * (1 - t) * t ** 2 * cp2[0] + t ** 3 * ex)
        y = ((1 - t) ** 3 * sy + 3 * (1 - t) ** 2 * t * cp1[1] +
             3 * (1 - t) * t ** 2 * cp2[1] + t ** 3 * ey)

        x += random.uniform(-0.5, 0.5)
        y += random.uniform(-0.5, 0.5)
        points.append((round(float(x), 2), round(float(y), 2)))

    return points


async def _get_cdp_session(page):
    """Lấy CDP session để gửi event chuột ở tầng thấp nhất (không thể bị phát hiện)."""
    try:
        client = await page.context.new_cdp_session(page)
        return client
    except Exception as e:
        _log(f"Không thể tạo CDP session: {e}")
        return None


async def _cdp_mouse_event(cdp, event_type, x, y, button='left', click_count=0, buttons_mask=0):
    """Gửi sự kiện chuột qua CDP Input.dispatchMouseEvent — không thể phát hiện automation."""
    params = {
        'type': event_type,
        'x': float(x),
        'y': float(y),
        'button': button if event_type != 'mouseMoved' else 'none',
        'clickCount': click_count,
        'buttons': buttons_mask,
        'pointerType': 'mouse',
    }
    await cdp.send('Input.dispatchMouseEvent', params)


async def _human_drag(page, start_x, start_y, end_x, end_y):
    """Kéo chuột bằng API Native CDP để đạt tốc độ phản hồi tối ưu trên VPS:
    - Quỹ đạo Ease-In-Out
    - Hiện tượng vung tay quá đà (Overshoot) và kéo giật lại (Correction)
    - Run tay hình sin mượt tự nhiên
    - Sử dụng CDP session trực tiếp bypass độ trễ trung gian của Playwright
    """
    import math
    import time
    
    start_x = round(float(start_x), 2)
    start_y = round(float(start_y), 2)
    end_x = round(float(end_x), 2)
    end_y = round(float(end_y), 2)
    _log(f"Kéo chuột qua CDP Native: ({start_x:.1f}, {start_y:.1f}) -> ({end_x:.1f}, {end_y:.1f})")
    
    cdp = await _get_cdp_session(page)
    if not cdp:
        # Fallback về Playwright Mouse nếu CDP fail
        try:
            await page.mouse.move(start_x, start_y, steps=5)
            await asyncio.sleep(0.2)
            await page.mouse.down()
            await asyncio.sleep(0.2)
            await page.mouse.move(end_x, end_y, steps=25)
            await asyncio.sleep(0.2)
            await page.mouse.up()
            return
        except:
            return

    def precise_sleep(seconds):
        start = time.perf_counter()
        while True:
            remaining = seconds - (time.perf_counter() - start)
            if remaining <= 0:
                break
            if remaining > 0.0015:
                time.sleep(0.001)
            else:
                pass

    try:
        # 1. Di chuyển chuột đến điểm bắt đầu và nhấn xuống
        await _cdp_mouse_event(cdp, 'mouseMoved', start_x, start_y)
        await asyncio.sleep(random.uniform(0.15, 0.25))
        await _cdp_mouse_event(cdp, 'mousePressed', start_x, start_y, button='left', click_count=1, buttons_mask=1)
        await asyncio.sleep(random.uniform(0.18, 0.3))
        
        # Tính toán overshoot
        distance = end_x - start_x
        overshoot = random.uniform(3, 7) if distance > 30 else 0.0
        overshoot_x = end_x + overshoot
        
        # Tần số và biên độ run tay
        wave_freq = random.uniform(2.0, 3.5)
        wave_amp = random.uniform(0.3, 0.6)
        
        # PHÂN ĐOẠN 1: Kéo vượt mức (Overshoot)
        steps = random.randint(50, 70)
        for i in range(1, steps + 1):
            t = i / steps
            ease_t = t * t * (3 - 2 * t)
            
            x = start_x + (overshoot_x - start_x) * ease_t
            y = start_y + (end_y - start_y) * ease_t + math.sin(t * math.pi * wave_freq) * wave_amp + random.uniform(-0.15, 0.15)
            
            await _cdp_mouse_event(cdp, 'mouseMoved', x, y, button='left', buttons_mask=1)
            precise_sleep(random.uniform(0.006, 0.010))
            
        # Tạm nghỉ rất ngắn tại điểm quá đà
        if overshoot > 0:
            await asyncio.sleep(random.uniform(0.08, 0.14))
            
            # PHÂN ĐOẠN 2: Kéo lùi lại điểm đích (Correction)
            correction_steps = random.randint(12, 18)
            for i in range(1, correction_steps + 1):
                t = i / correction_steps
                ease_t = math.sin(t * math.pi / 2)
                
                x = overshoot_x - (overshoot_x - end_x) * ease_t
                y = end_y + math.sin((1.0 + t) * math.pi * wave_freq) * (wave_amp * 0.4) + random.uniform(-0.1, 0.1)
                
                await _cdp_mouse_event(cdp, 'mouseMoved', x, y, button='left', buttons_mask=1)
                precise_sleep(random.uniform(0.008, 0.012))
        
        # Thả lỏng chuột trước khi nhấc
        await asyncio.sleep(random.uniform(0.2, 0.35))
        await _cdp_mouse_event(cdp, 'mouseReleased', end_x, end_y, button='left', click_count=1, buttons_mask=0)
        await asyncio.sleep(random.uniform(0.5, 0.8))
        
    except Exception as drag_err:
        _log(f"Lỗi kéo chuột giả lập CDP: {drag_err}")
    finally:
        try:
            await cdp.detach()
        except:
            pass


# ═══════════════════════════════════════════════════════════════════
# PHẦN 3: PHÁT HIỆN VÀ GIẢI CAPTCHA TRÊN TRANG WEB
# ═══════════════════════════════════════════════════════════════════

async def detect_captcha(page):
    """Phát hiện CAPTCHA trên trang. Returns: (type, frame) hoặc (None, None)."""
    captcha_selectors = [
        '#captcha-verify-image',
        '.captcha_verify_img--wrapper',
        '.captcha_verify_container',
        '#captcha_container',
        '.secsdk-captcha-drag-icon',
        '[class*="captcha"]',
        '.verify-wrap',
        '#verify-bar-close',
    ]

    frames = [page] + page.frames

    for frame in frames:
        try:
            for sel in captcha_selectors:
                try:
                    elem = await frame.query_selector(sel)
                    if elem and await elem.is_visible():
                        _log(f"Phát hiện CAPTCHA (selector: {sel})")
                        
                        # Thử phân loại loại CAPTCHA dựa trên văn bản mô tả (instruction text)
                        desc_selectors = [
                            '.captcha_verify_desc',
                            '.verify-desc',
                            '.verify-tip',
                            '.captcha_verify_title',
                            '[class*="desc"]',
                            '[class*="tip"]',
                            '[class*="title"]'
                        ]
                        
                        captcha_text = ""
                        for desc_sel in desc_selectors:
                            try:
                                desc_elem = await frame.query_selector(desc_sel)
                                if desc_elem and await desc_elem.is_visible():
                                    text = await desc_elem.inner_text()
                                    if text:
                                        captcha_text = text.lower()
                                        break
                            except:
                                continue
                                
                        _log(f"Văn bản mô tả CAPTCHA: '{captcha_text}'")
                        
                        # Kiểm tra xem có chứa class hoặc selector xoay không
                        has_rotate_class = False
                        try:
                            if await frame.query_selector('.captcha_verify_img_rotate, img[class*="rotate"], img[class*="whirl"]'):
                                has_rotate_class = True
                        except:
                            pass
                            
                        # Phân loại dựa trên mô tả hoặc class
                        if has_rotate_class or any(x in captcha_text for x in ['xoay', 'rotate', 'direction', 'upright', 'quay', 'whirl']):
                            _log("Phân loại: Rotate CAPTCHA")
                            return 'rotate', frame
                        elif any(x in captcha_text for x in ['hình giống', 'shapes', 'shape match', 'chọn', 'click', 'thứ tự', 'order']):
                            _log("Phân loại: Shapes CAPTCHA")
                            return 'shapes', frame
                        else:
                            # Mặc định là slide
                            _log("Phân loại: Slide CAPTCHA (mặc định)")
                            return 'slide', frame
                except:
                    continue
        except:
            continue

    # Kiểm tra nội dung HTML
    try:
        content = await page.content()
        content_lower = content.lower()
        if ('captcha' in content_lower or 'security check' in content_lower) and len(content) < 60000:
            _log("Phát hiện Security Check / CAPTCHA trong HTML")
            return 'security_check', page
    except:
        pass

    return None, None


async def _get_captcha_images(frame):
    """Tìm và trả về URL ảnh background + piece từ CAPTCHA container."""
    bg_url, piece_url = None, None

    # Chiến lược 1: Tìm ảnh cụ thể theo selector
    selectors_pairs = [
        ('#captcha-verify-image', '.captcha_verify_img_slide, .captcha_verify_img_rotate, img[class*="slide"], img[class*="rotate"], img[class*="whirl"]'),
        ('.captcha_verify_img--wrapper img', 'img.captcha_verify_img_slide, img.captcha_verify_img_rotate, img[class*="slide"], img[class*="rotate"], img[class*="whirl"]'),
        ('img[draggable="false"]', 'img[class*="slide"], img[class*="rotate"], img[class*="whirl"]'),
    ]

    for bg_sel, piece_sel in selectors_pairs:
        try:
            bg = await frame.query_selector(bg_sel)
            if bg:
                bg_url = await bg.get_attribute('src')
            pc = await frame.query_selector(piece_sel)
            if pc:
                piece_url = await pc.get_attribute('src')
            if bg_url and piece_url:
                break
        except:
            continue

    # Chiến lược 2: Lấy TẤT CẢ ảnh trong container captcha nếu thiếu ảnh
    if not bg_url or not piece_url:
        try:
            containers = [
                '.captcha_verify_container img',
                '.verify-wrap img',
                '[class*="captcha"] img',
                '#captcha_container img',
            ]
            for container_sel in containers:
                imgs = await frame.query_selector_all(container_sel)
                urls = []
                for img in imgs:
                    src = await img.get_attribute('src')
                    if src and (src.startswith('http') or src.startswith('data:')):
                        urls.append(src)
                if len(urls) >= 2:
                    bg_url, piece_url = urls[0], urls[1]
                    break
                elif len(urls) == 1:
                    bg_url = urls[0]
                    break
        except:
            pass

    return bg_url, piece_url


async def _download_image(page_or_frame, url):
    """Tải ảnh thông qua browser context (bypass CORS) sử dụng page hoặc frame."""
    if url.startswith('data:'):
        try:
            b64_data = url.split(',', 1)[1]
            return base64.b64decode(b64_data)
        except:
            return None

    try:
        result = await page_or_frame.evaluate("""async (url) => {
            try {
                const resp = await fetch(url);
                const blob = await resp.blob();
                return new Promise((resolve) => {
                    const reader = new FileReader();
                    reader.onload = () => resolve(reader.result);
                    reader.readAsDataURL(blob);
                });
            } catch(e) { return null; }
        }""", url)

        if result and result.startswith('data:'):
            b64_data = result.split(',', 1)[1]
            return base64.b64decode(b64_data)
    except:
        pass

    # Fallback: requests trực tiếp
    try:
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="chrome120")
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.content
    except:
        try:
            import requests
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.content
        except:
            pass
    return None


async def _get_slider_element(frame):
    """Tìm nút kéo slider."""
    slider_selectors = [
        '.secsdk-captcha-drag-icon',
        '.captcha-slider-btn',
        'span[class*="secsdk-captcha-drag-icon"]',
        '[class*="slider"] button',
        '[class*="drag-icon"]',
        '.verify-drag-button',
        '[class*="captcha_verify_slide--slider-button"]',
    ]
    for sel in slider_selectors:
        try:
            elem = await frame.query_selector(sel)
            if elem and await elem.is_visible():
                return elem
        except:
            continue
    return None


async def solve_slide_captcha(page, frame):
    """Giải Slide Puzzle CAPTCHA hoàn toàn tự động."""
    _log("Bắt đầu giải Slide Puzzle...")

    # Lưu ảnh chụp màn hình đầy đủ để debug
    try:
        await page.screenshot(path="debug_full_page.png")
        _log("Saved debug_full_page.png")
    except Exception as e:
        _log(f"Lỗi chụp màn hình full page: {e}")

    # 0. Giữ nguyên kích thước viewport để tránh Secsdk detect resize
    original_viewport = page.viewport_size
    window_id = None
    cdp_client = None

    # 0b. Inject stealth (Đã tắt để tránh xung đột với cloakbrowser)
    # try:
    #     await page.evaluate("""() => {
    #         Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    #         delete window.__playwright;
    #         delete window.__pw_manual;
    #         const origQuery = window.navigator.permissions.query;
    #         window.navigator.permissions.query = (parameters) => (
    #             parameters.name === 'notifications' ?
    #             Promise.resolve({ state: Notification.permission }) :
    #             origQuery(parameters)
    #         );
    #         Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    #         Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US', 'en'] });
    #     }""")
    # except:
    #     pass

    try:
        # 1. Lấy URL ảnh
        bg_url, piece_url = await _get_captcha_images(frame)
        if not bg_url:
            _log("Không tìm thấy ảnh CAPTCHA")
            return False

        _log(f"Ảnh: bg={'có' if bg_url else 'không'}, piece={'có' if piece_url else 'không'}")

        # 2. Tải ảnh (Sử dụng frame context để tránh lỗi CORS/CSP của top page)
        bg_bytes = await _download_image(frame, bg_url)
        piece_bytes = await _download_image(frame, piece_url) if piece_url else None

        if not bg_bytes:
            _log("Không tải được ảnh background")
            return False

        # In các ảnh để debug
        try:
            all_imgs = await frame.query_selector_all('img')
            for idx, img in enumerate(all_imgs):
                box = await img.bounding_box()
                cls = await img.get_attribute('class')
                src = await img.get_attribute('src')
                _log(f"DEBUG IMG {idx}: class='{cls}', box={box}, src_len={len(src) if src else 0}")
        except Exception as e:
            _log(f"DEBUG IMGS ERR: {e}")

        # 3. Tìm offset bằng thuật toán OpenCV
        offset = None
        if piece_bytes:
            offset = PuzzleSolver.find_offset(bg_bytes, piece_bytes)
        else:
            offset = GapDetector.find_gap_x(bg_bytes)

        if offset is None:
            _log("Không tính được offset, dùng giá trị ước lượng")
            offset = random.randint(80, 200)

        # 4. Tìm slider (chờ nó re-render ở viewport mới)
        await asyncio.sleep(0.5)
        slider = await _get_slider_element(frame)
        if not slider:
            _log("Không tìm thấy nút kéo")
            return False

        slider_box = await slider.bounding_box()
        if not slider_box:
            return False

        # 5. Tính tỷ lệ scale giữa ảnh gốc và hiển thị
        scale = 1.0
        container_box = None
        try:
            bg_elem = await frame.query_selector('#captcha-verify-image, .captcha_verify_img--wrapper img, [class*="captcha"] img')
            if bg_elem:
                container_box = await bg_elem.bounding_box()
                if container_box:
                    raw = np.frombuffer(bg_bytes, dtype="uint8")
                    img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
                    if img is not None:
                        scale = container_box['width'] / img.shape[1]
                        _log(f"Container: {container_box['width']:.0f}x{container_box['height']:.0f}, Ảnh gốc: {img.shape[1]}x{img.shape[0]}, Scale: {scale:.3f}")
        except:
            pass

        # Tính offset bù trừ (nếu puzzle piece không bắt đầu ở tọa độ X=0)
        piece_start_x = 0
        try:
            piece_elem = await frame.query_selector('.captcha_verify_img_slide, img[class*="slide"]')
            if piece_elem and container_box:
                piece_box = await piece_elem.bounding_box()
                if piece_box:
                    piece_start_x = piece_box['x'] - container_box['x']
                    # Nếu âm hoặc quá nhỏ thì bỏ qua (do sai số rendering)
                    if piece_start_x < 2:
                        piece_start_x = 0
                    _log(f"Piece start X (DOM): {piece_start_x:.1f}px")
        except:
            pass

        # 6. Tính toạ độ kéo
        # Vì frame có thể là iframe, ta cần tìm vị trí của iframe trong trang chính
        frame_offset_x = 0
        frame_offset_y = 0
        try:
            if frame != page:
                frame_element = await frame.frame_element()
                if frame_element:
                    frame_box = await frame_element.bounding_box()
                    if frame_box:
                        frame_offset_x = frame_box['x']
                        frame_offset_y = frame_box['y']
                        _log(f"Iframe offset found: x={frame_offset_x:.1f}, y={frame_offset_y:.1f}")
        except Exception as fe_err:
            _log(f"Không lấy được iframe offset: {fe_err}")

        start_x = slider_box['x'] + slider_box['width'] / 2 + random.uniform(-5, 5)
        start_y = slider_box['y'] + slider_box['height'] / 2 + random.uniform(-3, 3)
        
        # distance = (khoảng cách trên ảnh gốc * scale) - vị trí ban đầu của mảnh ghép
        distance = float(offset * scale) - piece_start_x
        target_x = start_x + distance
        target_y = start_y + random.uniform(-2, 2)

        _log(f"Kéo: offset={offset}px, scale={scale:.3f}, distance={distance:.2f}px")
        _log(f"Slider box: x={slider_box['x']:.0f}, y={slider_box['y']:.0f}, w={slider_box['width']:.0f}")
        _log(f"Start (Page-space): ({start_x:.1f}, {start_y:.1f}) → End (Page-space): ({target_x:.1f}, {target_y:.1f})")

        # 7. Kéo giống người thật (qua CDP)
        await _human_drag(page, start_x, start_y, target_x, target_y)

        await asyncio.sleep(2)
        return True
        
    finally:
        pass


async def solve_rotate_captcha(page, frame):
    """Giải Rotate CAPTCHA bằng cách tính góc qua OpenCV hoặc dự phòng thử nhiều góc."""
    _log("Bắt đầu giải Rotate Puzzle...")

    # 0. PHÓNG TO viewport để CAPTCHA hiển thị lớn, tọa độ chính xác hơn
    original_viewport = page.viewport_size
    window_id = None
    cdp_client = None
    try:
        cdp_client = await page.context.new_cdp_session(page)
        res = await cdp_client.send('Browser.getWindowForTarget')
        window_id = res.get('windowId')
        
        if window_id:
            await cdp_client.send('Browser.setWindowBounds', {
                'windowId': window_id,
                'bounds': {'windowState': 'maximized'}
            })
            _log("Đã phóng to cửa sổ OS (Maximized)")
            
        await page.set_viewport_size({"width": 1280, "height": 800})
        _log(f"Phóng to viewport để xoay: {original_viewport} → 1280x800")
        await asyncio.sleep(2.0)  # Chờ CAPTCHA re-render ở kích thước mới
    except Exception as vp_err:
        _log(f"Không resize được viewport/window: {vp_err}")

    try:
        slider = await _get_slider_element(frame)
        if not slider:
            _log("Không tìm thấy slider")
            return False

        slider_box = await slider.bounding_box()
        if not slider_box:
            return False

        # Đo chiều rộng track
        track_width = 260
        try:
            track = await frame.query_selector('[class*="slider-track"], [class*="drag-track"], [class*="captcha_verify_slide--slider"]')
            if track:
                tb = await track.bounding_box()
                if tb:
                    track_width = tb['width']
        except:
            pass

        # 1. Thử giải bằng thuật toán xoay ảnh OpenCV (Độ chính xác cao)
        try:
            bg_url, piece_url = await _get_captcha_images(frame)
            if bg_url and piece_url:
                _log("Tải ảnh xoay để xử lý...")
                bg_bytes = await _download_image(frame, bg_url)
                piece_bytes = await _download_image(frame, piece_url)
                
                if bg_bytes and piece_bytes:
                    best_angle = RotateSolver.find_rotation_angle(bg_bytes, piece_bytes)
                    if best_angle is not None:
                        # Thử hướng 1 (Thuận)
                        sx = slider_box['x'] + slider_box['width'] / 2
                        sy = slider_box['y'] + slider_box['height'] / 2
                        dist = int((best_angle / 360.0) * track_width)
                        
                        _log(f"Thử xoay OpenCV hướng thuận: góc {best_angle}°, kéo {dist}px")
                        await _human_drag(page, sx, sy, sx + dist, sy)
                        await asyncio.sleep(2)
                        
                        captcha_type, _ = await detect_captcha(page)
                        if captcha_type is None:
                            _log("✅ Giải thành công Rotate CAPTCHA qua OpenCV hướng thuận!")
                            return True
                            
                        # Thử hướng 2 (Nghịch: 360 - angle) nếu hướng 1 thất bại
                        _log("Hướng thuận thất bại, thử hướng nghịch...")
                        await asyncio.sleep(1)
                        
                        # Cập nhật slider_box mới
                        slider = await _get_slider_element(frame)
                        if slider:
                            slider_box = await slider.bounding_box() or slider_box
                            
                        sx = slider_box['x'] + slider_box['width'] / 2
                        sy = slider_box['y'] + slider_box['height'] / 2
                        dist_inv = int(((360.0 - best_angle) / 360.0) * track_width)
                        
                        _log(f"Thử xoay OpenCV hướng nghịch: góc {360 - best_angle}°, kéo {dist_inv}px")
                        await _human_drag(page, sx, sy, sx + dist_inv, sy)
                        await asyncio.sleep(2)
                        
                        captcha_type, _ = await detect_captcha(page)
                        if captcha_type is None:
                            _log("✅ Giải thành công Rotate CAPTCHA qua OpenCV hướng nghịch!")
                            return True
        except Exception as opencv_err:
            _log(f"Lỗi khi giải Rotate bằng OpenCV: {opencv_err}")

        # 2. Dự phòng: Thử nhiều góc ngẫu nhiên (Trial-and-error)
        _log("Bắt đầu thử giải bằng kịch bản dự phòng (Trial-and-error)...")
        for attempt, ratio in enumerate([0.35, 0.55, 0.25, 0.70, 0.45]):
            slider = await _get_slider_element(frame)
            if not slider:
                break
            slider_box = await slider.bounding_box() or slider_box
            
            sx = slider_box['x'] + slider_box['width'] / 2
            sy = slider_box['y'] + slider_box['height'] / 2
            dist = int(track_width * ratio)

            _log(f"Rotate lần {attempt + 1}: kéo {dist}px ({ratio * 100:.0f}%)")
            await _human_drag(page, sx, sy, sx + dist, sy)
            await asyncio.sleep(2)

            captcha_type, _ = await detect_captcha(page)
            if captcha_type is None:
                _log("✅ Giải thành công Rotate CAPTCHA bằng dự phòng!")
                return True
            await asyncio.sleep(0.5)

        return False
        
    finally:
        # 8. LUÔN LUÔN thu nhỏ viewport về kích thước gốc
        if cdp_client and window_id:
            try:
                await cdp_client.send('Browser.setWindowBounds', {
                    'windowId': window_id,
                    'bounds': {'windowState': 'normal', 'width': 400, 'height': 850}
                })
                _log("Đã thu nhỏ cửa sổ OS")
            except:
                pass
                
        if original_viewport:
            try:
                await page.set_viewport_size(original_viewport)
                _log(f"Khôi phục viewport: {original_viewport['width']}x{original_viewport['height']}")
            except:
                pass


async def handle_security_check(page):
    """Xử lý Security Check page."""
    _log("Xử lý Security Check...")

    for attempt in range(3):
        await asyncio.sleep(random.uniform(2, 4))

        # Mô phỏng chuột
        try:
            await page.mouse.move(random.randint(100, 400), random.randint(100, 400))
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await page.mouse.wheel(0, random.randint(100, 300))
            await asyncio.sleep(random.uniform(0.3, 0.8))
        except:
            pass

        try:
            await page.goto(page.url, timeout=30000, wait_until='domcontentloaded')
            await asyncio.sleep(3)
        except:
            continue

        content = await page.content()
        if 'Security Check' not in content and 'captcha' not in content.lower():
            _log("Security Check passed!")
            return True

        # Nếu xuất hiện CAPTCHA thực, chuyển sang giải
        ct, cf = await detect_captcha(page)
        if ct and ct != 'security_check':
            return await _solve_by_type(page, ct, cf)

    return False


async def _solve_by_type(page, captcha_type, captcha_frame):
    """Dispatch giải CAPTCHA theo loại."""
    if captcha_type == 'security_check':
        return await handle_security_check(page)
    elif captcha_type == 'slide':
        return await solve_slide_captcha(page, captcha_frame)
    elif captcha_type == 'rotate':
        return await solve_rotate_captcha(page, captcha_frame)
    else:
        _log(f"Loại CAPTCHA không hỗ trợ hoặc tự động reload: {captcha_type}")
        return False


# ═══════════════════════════════════════════════════════════════════
# PHẦN 4: ENTRY POINT CHÍNH
# ═══════════════════════════════════════════════════════════════════

async def solve_captcha(page, captcha_type=None, captcha_frame=None):
    """Phát hiện và giải CAPTCHA. Returns True nếu thành công."""
    if captcha_type is None:
        captcha_type, captcha_frame = await detect_captcha(page)

    if captcha_type is None:
        return True  # Không có CAPTCHA

    if captcha_frame is None:
        captcha_frame = page

    success = await _solve_by_type(page, captcha_type, captcha_frame)

    if success:
        await asyncio.sleep(2)
        new_type, _ = await detect_captcha(page)
        if new_type is None:
            _log("✅ CAPTCHA đã được giải thành công!")
            return True
        else:
            _log(f"⚠️ CAPTCHA vẫn còn (loại: {new_type})")
            return False

    return False


async def solve_captcha_with_retry(page, max_retries=3):
    """Giải CAPTCHA với retry logic + exponential backoff."""
    for attempt in range(max_retries):
        ct, cf = await detect_captcha(page)
        if ct is None:
            return True

        _log(f"Lần thử {attempt + 1}/{max_retries}...")
        success = await solve_captcha(page, ct, cf)
        if success:
            return True

        # Backoff
        wait = (attempt + 1) * 2 + random.uniform(0, 2)
        _log(f"Đợi {wait:.1f}s trước khi thử lại...")
        await asyncio.sleep(wait)

        # Thử click nút refresh của CAPTCHA trước khi reload cả trang
        refreshed = False
        if cf:
            try:
                refresh_btn = await cf.query_selector('.secsdk-captcha-refresh, a[class*="refresh"], [class*="refresh"]')
                if refresh_btn and await refresh_btn.is_visible():
                    _log("Tìm thấy nút refresh CAPTCHA, đang click để đổi mã...")
                    await refresh_btn.click()
                    await asyncio.sleep(3)
                    refreshed = True
            except Exception as e:
                _log(f"Không click được nút refresh CAPTCHA: {e}")

        if not refreshed:
            try:
                _log("Reloading toàn bộ trang...")
                await page.reload(wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)
            except:
                pass

    _log(f"❌ Không thể giải CAPTCHA sau {max_retries} lần thử")
    return False
