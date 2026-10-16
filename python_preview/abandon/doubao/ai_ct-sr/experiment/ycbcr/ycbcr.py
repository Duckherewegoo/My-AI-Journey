import os.path as path
dirname__ = path.dirname(path.abspath(__file__))

from PIL import Image
from matplotlib import pyplot as plt

rgb_image = Image.open(path.join(dirname__, 'rgb.png')).convert('RGB')
ycbcr_image = rgb_image.copy().convert('YCbCr')

y_image = ycbcr_image.getchannel('Y')
cb_image = ycbcr_image.getchannel('Cb')
cr_image = ycbcr_image.getchannel('Cr')

pos = 221
def imshow(img):
    global pos
    plt.subplot(pos)
    plt.imshow(img, cmap='gray' if img.mode == 'L' else None)
    plt.yticks([])
    plt.xticks([])
    pos += 1

list(map(imshow, (rgb_image, y_image, cb_image, cr_image)))
plt.show()
