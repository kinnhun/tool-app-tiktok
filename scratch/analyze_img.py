import cv2
import numpy as np

img = cv2.imread("scratch/after_click.png")
if img is not None:
    print(f"Image shape: {img.shape}")
    # Chuyển sang grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Lấy thông số độ sáng trung bình
    print(f"Mean brightness: {np.mean(gray)}")
    # Xem có phần nào là màu đen (modal overlay) không
    # Overlay modal của TikTok thường có màu đen mờ (rgba(0,0,0,0.5))
    pass
else:
    print("Could not read image")
