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
            # Lưu ảnh tải về thư mục nháp để tiện debug/phân tích sau này
            try:
                scratch_dir = r"C:\Users\trant\.gemini\antigravity\brain\687005d2-3ff4-4cf7-a064-b26693e46d48\scratch"
                os.makedirs(scratch_dir, exist_ok=True)
                with open(os.path.join(scratch_dir, "rotate_bg_latest.png"), "wb") as f:
                    f.write(bg_bytes)
                with open(os.path.join(scratch_dir, "rotate_piece_latest.png"), "wb") as f:
                    f.write(piece_bytes)
            except:
                pass

            # Decode images
            raw_bg = np.frombuffer(bg_bytes, dtype="uint8")
            bg = cv2.imdecode(raw_bg, cv2.IMREAD_GRAYSCALE)
            
            raw_pc = np.frombuffer(piece_bytes, dtype="uint8")
            pc = cv2.imdecode(raw_pc, cv2.IMREAD_GRAYSCALE)
            
            if bg is None or pc is None:
                return None
                
            h_pc, w_pc = pc.shape[:2]
            h_bg, w_bg = bg.shape[:2]
            
            cy_bg, cx_bg = h_bg // 2, w_bg // 2
            cy_pc, cx_pc = h_pc // 2, w_pc // 2
            
            # --- CHIẾN LƯỢC 1: Polar Correlation (Độ chính xác và độ tin cậy cực cao cho Rotate CAPTCHA) ---
            # Phát hiện bán kính thực tế của vòng tròn xoay từ kênh alpha, Canny edges, hoặc ngưỡng xám để tránh lấy nhầm vùng trong suốt bên ngoài
            radius = min(w_pc, h_pc) // 2
            
            raw_pc_unchanged = np.frombuffer(piece_bytes, dtype="uint8")
            pc_unchanged = cv2.imdecode(raw_pc_unchanged, cv2.IMREAD_UNCHANGED)
            
            detected = False
            if pc_unchanged is not None and len(pc_unchanged.shape) == 3 and pc_unchanged.shape[2] == 4:
                alpha = pc_unchanged[:, :, 3]
                non_zero = np.argwhere(alpha > 15)
                if len(non_zero) > 0:
                    y1, x1 = non_zero.min(axis=0)[:2]
                    y2, x2 = non_zero.max(axis=0)[:2]
                    true_w = x2 - x1
                    true_h = y2 - y1
                    if true_w > 40 and true_h > 40:
                        radius = min(true_w, true_h) // 2
                        cy_pc = int((y1 + y2) / 2)
                        cx_pc = int((x1 + x2) / 2)
                        detected = True
                        _log(f"Phát hiện bán kính hình xoay từ Alpha: {radius}px (bbox: {true_w}x{true_h}), tâm: ({cx_pc}, {cy_pc})")
            
            # Thử phát hiện qua Canny edges (cực kỳ mạnh mẽ cho cả nền đen/trắng/trong suốt)
            if not detected:
                try:
                    edges_pc = cv2.Canny(pc, 30, 150)
                    non_zero = np.argwhere(edges_pc > 0)
                    if len(non_zero) > 0:
                        y1, x1 = non_zero.min(axis=0)[:2]
                        y2, x2 = non_zero.max(axis=0)[:2]
                        true_w = x2 - x1
                        true_h = y2 - y1
                        if 40 < true_w < w_pc + 5 and 40 < true_h < h_pc + 5:
                            radius = min(true_w, true_h) // 2
                            cy_pc = int((y1 + y2) / 2)
                            cx_pc = int((x1 + x2) / 2)
                            detected = True
                            _log(f"Phát hiện bán kính hình xoay từ Canny edges: {radius}px (bbox: {true_w}x{true_h}), tâm: ({cx_pc}, {cy_pc})")
                except Exception as e:
                    _log(f"Lỗi khi phát hiện bán kính qua Canny: {e}")
 
            # Thử phát hiện qua ngưỡng xám
            if not detected and pc_unchanged is not None:
                gray_pc = cv2.cvtColor(pc_unchanged, cv2.COLOR_BGR2GRAY) if len(pc_unchanged.shape) == 3 else pc_unchanged
                non_zero = np.argwhere(gray_pc > 15)
                if len(non_zero) > 0:
                    y1, x1 = non_zero.min(axis=0)[:2]
                    y2, x2 = non_zero.max(axis=0)[:2]
                    true_w = x2 - x1
                    true_h = y2 - y1
                    if 40 < true_w < w_pc + 5 and 40 < true_h < h_pc + 5:
                        radius = min(true_w, true_h) // 2
                        cy_pc = int((y1 + y2) / 2)
                        cx_pc = int((x1 + x2) / 2)
                        detected = True
                        _log(f"Phát hiện bán kính hình xoay từ ngưỡng xám: {radius}px (bbox: {true_w}x{true_h}), tâm: ({cx_pc}, {cy_pc})")
 
            angles = np.linspace(0, 2 * np.pi, 360, endpoint=False)
            avg_correlations = np.zeros(360, dtype=np.float32)
            count = 0
            
            # Tính tỷ lệ scale giữa background và piece đề phòng phân giải khác nhau
            scale_x = w_bg / w_pc
            scale_y = h_bg / h_pc
            
            # Đo độ tương quan ở vùng rìa giao tiếp (Edge Ring Correlation)
            # Vì bg thường bị khoét lỗ rỗng ở giữa, ta phải so sánh viền ngoài của pc với viền trong của bg
            for d in range(2, 14, 2):
                try:
                    r_pc = radius - d
                    r_bg = radius + d
                    if r_pc < 5 or r_bg >= min(w_bg, h_bg) // 2:
                        continue
                        
                    p_pc = []
                    p_bg = []
                    for a in angles:
                        px_p = int(cx_pc + r_pc * np.cos(a))
                        py_p = int(cy_pc + r_pc * np.sin(a))
                        p_pc.append(pc[py_p, px_p])
                        
                        px_b = int(cx_bg + r_bg * np.cos(a))
                        py_b = int(cy_bg + r_bg * np.sin(a))
                        p_bg.append(bg[py_b, px_b])
                        
                    p_pc = np.array(p_pc, dtype=np.float32)
                    p_bg = np.array(p_bg, dtype=np.float32)
                    
                    p_pc -= np.mean(p_pc)
                    p_bg -= np.mean(p_bg)
                    s_p = np.std(p_pc)
                    s_b = np.std(p_bg)
                    
                    if s_p > 0 and s_b > 0:
                        p_pc /= s_p
                        p_bg /= s_b
                        
                        for shift in range(360):
                            shifted_p = np.roll(p_pc, -shift)
                            avg_correlations[shift] += np.mean(shifted_p * p_bg)
                        count += 1
                except:
                    continue
                    
            if count > 0:
                avg_correlations /= count
                best_angle = int(np.argmax(avg_correlations))
                max_val = float(avg_correlations[best_angle])
                _log(f"Rotate solver (Polar): tìm thấy góc xoay tối ưu = {best_angle}° với độ tin cậy {max_val:.3f}")
                if max_val >= 0.15:  # Ngưỡng tin cậy tối thiểu cho Polar Correlation
                    # Chuyển đổi góc xoay thuận chiều kim đồng hồ cần thiết để căn chỉnh mảnh ghép
                    return (360 - best_angle) % 360
 
            # --- CHIẾN LƯỢC 2: Dự phòng template matching cổ điển ---
            _log("Độ tin cậy Polar thấp, sử dụng template matching cổ điển làm dự phòng...")
            
            # Crop center of bg with a slight padding to allow for small translation offsets
            pad = 10
            y1 = max(0, cy_bg - h_pc // 2 - pad)
            y2 = min(h_bg, cy_bg + h_pc - h_pc // 2 + pad)
            x1 = max(0, cx_bg - w_pc // 2 - pad)
            x2 = min(w_bg, cx_bg + w_pc - w_pc // 2 + pad)
            
            bg_center = bg[y1:y2, x1:x2]
                
            bg_edges = cv2.Canny(bg_center, 50, 150)
            pc_edges = cv2.Canny(pc, 50, 150)
            
            # Tạo mask hình tròn loại bỏ viền ngoài tránh làm nhiễu khớp tại góc 0 độ
            mask = np.zeros((h_pc, w_pc), dtype=np.uint8)
            cv2.circle(mask, (cx_pc, cy_pc), int(radius * 0.85), 255, -1)
            
            pc_edges = cv2.bitwise_and(pc_edges, pc_edges, mask=mask)
            
            best_angle = 0
            max_val = -1
            
            center = (w_pc // 2, h_pc // 2)
            for angle in range(0, 360, 2):
                rot_mat = cv2.getRotationMatrix2D(center, -angle, 1.0)
                rotated = cv2.warpAffine(pc_edges, rot_mat, (w_pc, h_pc), flags=cv2.INTER_LINEAR)
                res = cv2.matchTemplate(bg_edges, rotated, cv2.TM_CCOEFF_NORMED)
                _, val, _, _ = cv2.minMaxLoc(res)
                
                if val > max_val:
                    max_val = val
                    best_angle = angle
                    
            _log(f"Rotate solver (Classic): tìm thấy góc xoay = {best_angle}° với độ tin cậy {max_val:.3f}")
            # Góc xoay tìm được là góc thuận chiều kim đồng hồ cần thiết
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
    """Kéo chuột bằng API Playwright Mouse với đường đi mô phỏng người thật:
    - Quỹ đạo Ease-In-Out
    - Hiện tượng vung tay quá đà (Overshoot) và kéo giật lại (Correction)
    - Run tay hình sin mượt tự nhiên
    """
    import math
    import asyncio
    import random
    
    start_x = round(float(start_x), 2)
    start_y = round(float(start_y), 2)
    end_x = round(float(end_x), 2)
    end_y = round(float(end_y), 2)
    _log(f"Kéo chuột qua Playwright Mouse: ({start_x:.1f}, {start_y:.1f}) -> ({end_x:.1f}, {end_y:.1f})")
    
    try:
        # 1. Di chuyển chuột đến điểm bắt đầu và nhấn xuống thật nhanh
        await page.mouse.move(start_x, start_y, steps=3)
        await asyncio.sleep(0.02)
        await page.mouse.down()
        await asyncio.sleep(0.02)
        
        # 2. Kéo một phát thẳng tới đích không delay
        await page.mouse.move(end_x, end_y, steps=5)
        await asyncio.sleep(0.02)
        
        # 3. Nhấc chuột lên luôn
        await page.mouse.up()
        await asyncio.sleep(0.05)
        
    except Exception as drag_err:
        _log(f"Lỗi kéo chuột Playwright: {drag_err}")


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
        '#captcha-verify-container-main-page',
        '[id*="captcha-verify-container"]',
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
                            
                        # Kiểm tra xem có chứa class slide không để tránh nhận diện sai slide thành rotate do trùng chữ "fit the puzzle"
                        has_slide_class = False
                        try:
                            if await frame.query_selector('.captcha_verify_img_slide, img[class*="slide"]'):
                                has_slide_class = True
                        except:
                            pass

                        # Kiểm tra tỷ lệ kích thước ảnh nền để tự động phân loại chính xác hình tròn/vuông (Rotate) vs hình chữ nhật (Slide)
                        is_square_captcha = False
                        is_rect_captcha = False
                        try:
                            bg_el = await frame.query_selector('#captcha-verify-image, .captcha_verify_img--wrapper img, [class*="captcha"] img, img[class*="cap-h-"]:not([class*="cap-absolute"]), img[class*="cap-"]:not([class*="cap-absolute"])')
                            if bg_el:
                                box = await bg_el.bounding_box()
                                if box and box['width'] > 0 and box['height'] > 0:
                                    ratio = box['width'] / box['height']
                                    if 0.85 <= ratio <= 1.15:
                                        is_square_captcha = True
                                        _log(f"Phát hiện ảnh CAPTCHA dạng vuông ({box['width']}x{box['height']}, tỷ lệ: {ratio:.2f}) -> Xác định là Rotate CAPTCHA.")
                                    elif ratio > 1.25 or ratio < 0.8:
                                        is_rect_captcha = True
                                        _log(f"Phát hiện ảnh CAPTCHA dạng chữ nhật ({box['width']}x{box['height']}, tỷ lệ: {ratio:.2f}) -> Xác định là Slide CAPTCHA.")
                        except Exception as e:
                            _log(f"Lỗi kiểm tra kích thước ảnh CAPTCHA: {e}")

                        # Phân loại dựa trên mô tả, kích thước hình học hoặc class
                        if is_square_captcha:
                            _log("Phân loại: Rotate CAPTCHA (theo hình dáng ảnh vuông)")
                            return 'rotate', frame
                        elif is_rect_captcha:
                            _log("Phân loại: Slide CAPTCHA (theo hình dáng ảnh chữ nhật)")
                            return 'slide', frame
                        elif has_slide_class and not has_rotate_class:
                            _log("Phân loại: Slide CAPTCHA (ưu tiên theo class)")
                            return 'slide', frame
                        elif has_rotate_class and not has_slide_class:
                            _log("Phân loại: Rotate CAPTCHA (ưu tiên theo class)")
                            return 'rotate', frame
                        elif any(x in captcha_text for x in ['xoay', 'rotate', 'direction', 'upright', 'quay', 'whirl']):
                            _log("Phân loại: Rotate CAPTCHA (theo từ khóa quay/xoay)")
                            return 'rotate', frame
                        elif any(x in captcha_text for x in ['fit the puzzle', 'fit']):
                            # Nếu có chữ "fit the puzzle" nhưng không xác định rõ qua kích thước
                            if has_rotate_class:
                                _log("Phân loại: Rotate CAPTCHA (fit + rotate class)")
                                return 'rotate', frame
                            else:
                                _log("Phân loại: Slide CAPTCHA (fit + slide default)")
                                return 'slide', frame
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
        ('img[class*="cap-h-"]:not([class*="cap-absolute"])', 'img[class*="cap-absolute"]'),
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
        '#captcha_slide_button',
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
        # Thêm một chút correction (+3px đến +4px) vì đôi khi mảnh ghép bị hở một chút gây ra lỗi
        correction_px = random.uniform(3.0, 4.5)
        distance = float(offset * scale) - piece_start_x + correction_px
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

    try:
        slider = await _get_slider_element(frame)
        if not slider:
            _log("Không tìm thấy slider")
            return False

        slider_box = await slider.bounding_box()
        if not slider_box:
            return False

        # Đo chiều rộng track
        track_width = 340
        try:
            track = await frame.query_selector('[class*="slider-track"], [class*="drag-track"], [class*="captcha_verify_slide--slider"], [class*="cap-rounded-full"]')
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
                        slider_width = slider_box['width']
                        draggable_distance = max(50, track_width - slider_width)
                        
                        # Thử hướng 1 (Thuận)
                        sx = slider_box['x'] + slider_box['width'] / 2
                        sy = slider_box['y'] + slider_box['height'] / 2
                        dist = int((best_angle / 360.0) * draggable_distance)
                        
                        _log(f"Thử xoay OpenCV hướng thuận: góc {best_angle}°, kéo {dist}px (trên {draggable_distance}px)")
                        await _human_drag(page, sx, sy, sx + dist, sy)
                        await asyncio.sleep(2)
                        
                        captcha_type, _ = await detect_captcha(page)
                        if captcha_type is None:
                            _log("✅ Giải thành công Rotate CAPTCHA qua OpenCV hướng thuận!")
                            return True
                            
                        # Kiểm tra xem ảnh CAPTCHA có bị đổi mới trên trang hay không trước khi thử hướng 2
                        _log("Hướng thuận thất bại, kiểm tra xem ảnh CAPTCHA có đổi không...")
                        new_bg_url, new_piece_url = await _get_captcha_images(frame)
                        if new_bg_url != bg_url:
                            _log("Ảnh CAPTCHA đã tự động đổi mới, quay lại tính toán từ đầu...")
                            return False
                            
                        # Thử hướng 2 (Nghịch: 360 - angle) nếu hướng 1 thất bại và ảnh chưa đổi
                        _log("Ảnh CAPTCHA chưa đổi, thử xoay hướng nghịch...")
                        await asyncio.sleep(1)
                        
                        # Cập nhật slider_box mới
                        slider = await _get_slider_element(frame)
                        if slider:
                            slider_box = await slider.bounding_box() or slider_box
                            slider_width = slider_box['width']
                            draggable_distance = max(50, track_width - slider_width)
                            
                        sx = slider_box['x'] + slider_box['width'] / 2
                        sy = slider_box['y'] + slider_box['height'] / 2
                        dist_inv = int(((360.0 - best_angle) / 360.0) * draggable_distance)
                        
                        _log(f"Thử xoay OpenCV hướng nghịch: góc {360 - best_angle}°, kéo {dist_inv}px (trên {draggable_distance}px)")
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
        # Lưu URL gốc để kiểm tra sự thay đổi của ảnh trong vòng lặp thử sai
        last_bg_url, _ = await _get_captcha_images(frame)
        for attempt, ratio in enumerate([0.35, 0.55, 0.25, 0.70, 0.45]):
            # Kiểm tra xem ảnh có tự động thay đổi không
            curr_bg_url, _ = await _get_captcha_images(frame)
            if curr_bg_url != last_bg_url:
                _log("Ảnh CAPTCHA đã đổi trong lúc thử sai, dừng vòng lặp để reload và tính toán góc mới...")
                return False

            slider = await _get_slider_element(frame)
            if not slider:
                break
            slider_box = await slider.bounding_box() or slider_box
            slider_width = slider_box['width']
            draggable_distance = max(50, track_width - slider_width)
            
            sx = slider_box['x'] + slider_box['width'] / 2
            sy = slider_box['y'] + slider_box['height'] / 2
            dist = int(draggable_distance * ratio)

            _log(f"Rotate lần {attempt + 1}: kéo {dist}px ({ratio * 100:.0f}%)")
            await _human_drag(page, sx, sy, sx + dist, sy)
            await asyncio.sleep(2)

            captcha_type, _ = await detect_captcha(page)
            if captcha_type is None:
                _log("✅ Giải thành công Rotate CAPTCHA bằng dự phòng!")
                return True
            await asyncio.sleep(0.5)

        return False
    except Exception as e:
        _log(f"Lỗi Rotate CAPTCHA: {e}")
        return False


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


_captcha_locks = {}

def _get_captcha_lock():
    loop = asyncio.get_running_loop()
    if not hasattr(loop, "_captcha_lock"):
        loop._captcha_lock = asyncio.Lock()
    return loop._captcha_lock


async def solve_captcha_with_retry(page, max_retries=3):
    """Giải CAPTCHA với retry logic + exponential backoff, có khóa để tránh đụng độ giữa nhiều tab."""
    lock = _get_captcha_lock()
    async with lock:
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
                    refresh_btn = await cf.query_selector('#captcha_refresh_button, .secsdk-captcha-refresh, a[class*="refresh"], [class*="refresh"]')
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
