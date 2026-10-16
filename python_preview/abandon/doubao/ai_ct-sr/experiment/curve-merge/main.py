import os.path as path
dirname__ = path.dirname(path.abspath(__file__))

import cv2 as cv

# LR 裁剪的左上方坐标 (x, y)
left_up = [64, 64]
# LR 裁剪的宽高 (w, h)
bbox = [64, 64]

SCALE = 4

LR_IMAGE = path.join(dirname__, 'lr.png')
SR_IMAGE = path.join(dirname__, 'sr.png')

lr_image = cv.imread(LR_IMAGE, cv.IMREAD_GRAYSCALE)
sr_image = cv.imread(SR_IMAGE, cv.IMREAD_GRAYSCALE)

# LR 裁剪
lr_cut = lr_image[
    left_up[1]:left_up[1] + bbox[1],
    left_up[0]:left_up[0] + bbox[0]
]

# SR 裁剪：坐标和尺寸都要 ×SCALE
sr_cut = sr_image[
    left_up[1] * SCALE:(left_up[1] + bbox[1]) * SCALE,
    left_up[0] * SCALE:(left_up[0] + bbox[0]) * SCALE
]

cv.imwrite('./lr_cut.png', lr_cut)
cv.imwrite('./bicubic_cut.png', cv.resize(lr_cut, None, fx=SCALE, fy=SCALE,
                                          interpolation=cv.INTER_CUBIC))
cv.imwrite('./sr_cut.png', sr_cut)
