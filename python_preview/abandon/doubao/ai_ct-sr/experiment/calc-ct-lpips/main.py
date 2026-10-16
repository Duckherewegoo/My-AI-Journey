import json
from tqdm import tqdm
import torchvision.transforms as transforms
from PIL import Image
import os
from nova.ct_lpips.ctlpips import get_ct_lpips
import sys
import os.path as path

dirname__ = path.dirname(path.abspath(__file__))

sys.path.append(path.join(dirname__))                       # current directory first
sys.path.append(path.join(dirname__, '../../nova'))


GroundTruth = r'/run/media/dake/Software/Projects/datasets/DeepLesion_Key_slices/val/HR/'

ct_filenames = os.listdir(GroundTruth)

Candidates = [
    {
        'name': 'ESPCN',
        'out_dir': r'/run/media/dake/Software/Projects/Graduation_Projects/codes/baselines/outputs_deeplesion/espcn/val_inference',
        'avg': 0.0,
    },
    {
        'name': 'EDSR',
        'out_dir': r'/run/media/dake/Software/Projects/Graduation_Projects/codes/baselines/outputs_deeplesion/edsr/val_inference',
        'avg': 0.0,
    },
    {
        'name': 'DWSR',
        'out_dir': r'/run/media/dake/Software/Projects/Graduation_Projects/codes/baselines/outputs_deeplesion/dwsr/val_inference',
        'avg': 0.0,
    },
    {
        'name': 'LUMWCNN',
        'out_dir': r'/run/media/dake/Software/Projects/Graduation_Projects/codes/nova/lu_mwcnn/output_deeplesion/val_inference',
        'avg': 0.0,
    },
]


step = 0

for fn in tqdm(ct_filenames, ncols=80):
    gt = transforms.ToTensor()(Image.open(path.join(GroundTruth, fn)).convert('L'))

    def get_sr_name(filename):
        return filename.replace('.png', '') + '_gray.png'

    for model in Candidates:
        sr_path = path.join(model['out_dir'], get_sr_name(fn))
        if not os.path.exists(sr_path):
            continue
        sr = transforms.ToTensor()(Image.open(sr_path).convert('L'))
        model['avg'] = (model['avg'] + get_ct_lpips(sr, gt)) / 2

    step += 1

    def report_status():
        avgs = ['%.4f' % float(x['avg']) for x in Candidates]
        print()
        print(avgs)

    if step % 100 == 0:
        report_status()

print('-- DONE --')
print(Candidates)


with open('./out.json', 'w') as f:
    f.write(json.dumps(Candidates, indent=2))

print('-- DONE --')
